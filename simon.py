import warnings
from datetime import date
from os import walk, remove, path
from pathlib import Path
import time
import matplotlib
import matplotlib.pyplot as plt
from multiprocessing import Process, Queue, Manager
from tkinter import Tk, Label
from tkinter import ttk


class Monitor:
    """
    Monitor and track a simulation. This class is meant to wrap
    all the variables of the simulation and store them in a single directory.
    It tracks networks, variables and constants, and saves graphs, data files,
    and network configurations. It also provides a live view to track the simulation.
    """

    def __init__(self, dir_name=None, super_directory=None, no_files=False, no_toggles=False):

        # create output directories
        if not no_files:
            self.dir_path = _generate_directory(dir_name, super_directory)
            self.data_path = f'{self.dir_path}/data'
            self.graphs_path = f'{self.dir_path}/graphs'
            self.networks_path = f'{self.dir_path}/networks'

            for d_path in (self.data_path, self.graphs_path, self.networks_path):
                _create_dir_path(d_path)

        self.grouped_trackers = {}
        self.ids = 0  # used to identify trackers
        self.live_view_process = None
        self.live_view_queue = None

        self.toggles = []

        if not no_toggles:
            toggles_window_title = dir_name if dir_name else 'Monitor toggles'
            self.live_view_toggle = Toggle(None, desc='Toggle live view', window_title=toggles_window_title)
            self.toggles.append(self.live_view_toggle)
            self.plot_toggle = self.add_toggle(name='Plot', desc='Plot trackers')

        self.monitor_vars = set()
        self.monitor_vars.update(set(vars(self).keys()))

    def tracker(self, ind_var_name, *dep_var_names, group_name='no_group', autosave=False):
        """
        Create a tracker object to track variables.
        A tracker is associated with one independent variable, and multiple dependent
        variables.
        :param ind_var_name: The independent variable name.
        :param dep_var_names: The dependent variable names.
        :param group_name: An optional group name. Multiple trackers
                                that belong to the same group will be plotted together.
        :param autosave: Enables autosave for the tracker.
        :return: A tracker object that has an update() method.
        """
        if not getattr(self, 'data_path', False):  # if no files
            dir_path = ''
            autosave = False
        elif group_name == 'no_group':
            dir_path = self.data_path
        else:
            dir_path = self.data_path + "/" + group_name
            _create_dir_path(dir_path)

        tracker = Tracker(self, self.ids, dir_path, ind_var_name, *dep_var_names, autosave=autosave)

        # increase self.ids
        self.ids += 1

        if group_name in self.grouped_trackers:
            self.grouped_trackers[group_name].append(tracker)
        else:
            self.grouped_trackers[group_name] = [tracker]

        return tracker

    def add_toggle(self, name='Toggle', desc='Press to toggle'):
        """
        Add a Toggle to the toggles window.
        :param name: Toggle name.
        :param desc: Toggle description.
        :return: A new Toggle object that has the method toggled().
        """
        toggle = Toggle(self.live_view_toggle, name=name, desc=desc)
        self.toggles.append(toggle)
        return toggle

    def close_toggles(self):
        """
        Close all toggles.
        """
        for toggle in self.toggles:
            toggle.close()

    def plot(self, *args):
        """
        Plot all groups or trackers in a single figure.
        :param args: either group names, or Tracker objects.
        :return: a matplotlib figure, only if return_figure is True.
        """
        _monitor_plot(self, *args)

    def open_live_view(self, update_rate=2):
        """
        Open a live view of the monitor in a different process.
        :param update_rate: how many graph updates to perform in a second.
        """
        # make self less recursive by removing monitor
        # reference from trackers
        for trackers in self.grouped_trackers.values():
            for tracker in trackers:
                tracker.monitor = None

        # also, remove toggle objects temporarily
        toggles = self.toggles
        live_view_toggle = self.live_view_toggle
        plot_toggle = self.plot_toggle
        self.toggles = None
        self.live_view_toggle = None
        self.plot_toggle = None

        # create a queue for communication
        self.live_view_queue = Queue()

        # create the process
        self.live_view_process = Process(target=_live_view_process,
                                         args=(self, self.live_view_queue, update_rate))
        self.live_view_process.start()

        # restore monitor reference to trackers
        for trackers in self.grouped_trackers.values():
            for tracker in trackers:
                tracker.monitor = self

        # restore toggle objects
        self.toggles = toggles
        self.live_view_toggle = live_view_toggle
        self.plot_toggle = plot_toggle

    def close_live_view(self):
        """
        Close the live view.
        """
        if not self.live_view_queue:  # means that live view is closed
            return

        self.live_view_queue.put(None)
        self.live_view_process.join()
        self.live_view_queue = None
        self.live_view_process = None

    def finalize(self):
        """
        Save all data tracked by this Monitor.
        This includes:
        - Config data file
        - Tracker .csv files
        - Network .pickle files
        - Graphs
        Also closes the live view if it remained open.
        """
        if not getattr(self, 'dir_path', False):  # if no files
            self.close_live_view()
            self.close_toggles()
            return

        # save tracked data
        for trackers in self.grouped_trackers.values():
            for tracker in trackers:
                if not tracker.autosave:
                    tracker.save()

        # save group graphs
        for group_name in self.grouped_trackers:
            if group_name != "no_group":
                figure, _ = _monitor_plot(self, group_name, return_figure_and_axs=True)
                figure.savefig(f'{self.graphs_path}/{group_name}.png', bbox_inches='tight')

        # save no-group graphs
        if "no_group" in self.grouped_trackers:
            for tracker in self.grouped_trackers["no_group"]:
                figure, _ = _monitor_plot(self, tracker, return_figure_and_axs=True)
                figure.savefig(f'{self.graphs_path}/'
                               f'{_determine_tracker_filename(tracker, self.graphs_path, ".png")}', bbox_inches='tight')

        # save config file
        self._save_config_file()

        # close live view
        self.close_live_view()

        # close toggles
        self.close_toggles()

    def load_from_dir(self, dir_path=None):
        """
        Load all monitor data already contained in dir_path.
        :param dir_path: if provided, this path is used instead of self.dir_path.
        """
        if not dir_path:
            if not getattr(self, 'dir_path', False):  # if no files
                raise Exception("No directory to load from!")
            dir_path = self.dir_path

        data_path = f'{dir_path}/data'
        config_path = f'{dir_path}/config.txt'

        # load data
        if path.exists(data_path):
            data_content = next(walk(data_path), [()] * 3)
            for group in data_content[1]:  # dir names
                group_path = f'{data_path}/{group}'
                for tracker_filename in next(walk(group_path), [()] * 3)[2]:
                    labels = tracker_filename.replace('+', '').split('-')
                    tracker = self.tracker(labels[0], *labels[1:], group_name=group)
                    _load_to_tracker(tracker, f'{group_path}/{tracker_filename}')

            for no_group_filename in data_content[2]:  # file names
                labels = no_group_filename.replace('+', '').split('-')
                tracker = self.tracker(labels[0], *labels[1:])
                _load_to_tracker(tracker, f'{data_path}/{no_group_filename}')

        # load config
        if path.exists(config_path):
            with open(config_path, 'r') as file:
                for line in file.readlines()[3:]:
                    line = line.replace('\n', '')
                    if len(line):
                        values = line.split(': ')
                        attr_name = values[0]
                        attr_value = values[1]
                        if attr_value.replace(".", "").replace("-", "").isnumeric():
                            attr_value = float(attr_value)

                        vars(self)[attr_name] = attr_value

    def _save_config_file(self):
        """
        Save attributes added to this object.
        These attributes are considered "configurations" and
        are written to a "config.txt" file.
        """
        with open(self.dir_path + "/" + "config.txt", 'w') as file:
            content = "-----------------\n" \
                      "   Config Data   \n" \
                      "-----------------\n"
            for var_name, var in vars(self).items():
                if var_name not in self.monitor_vars:
                    content += f"{var_name}: {str(var)}\n"
            file.write(content[:-1])


class Tracker:
    """
    Track variables and save them to .csv files.
    This class is a helper to the Monitor class.
    """

    def __init__(self, monitor: Monitor, _id: float, dir_path: str, ind_var_name: str, *dep_var_names, autosave=False):

        self._id = _id
        self.dir_path = dir_path

        # raise errors if needed
        if not len(dep_var_names):
            raise ValueError("No dependent variable names provided to tracker!")

        for name in dep_var_names:
            if type(name) != str:
                raise ValueError(f"Variable name must be a string, not {type(name)}!")

        self.monitor = monitor
        self.ind_var_name = ind_var_name
        self.dep_var_names = list(dep_var_names)
        self.data = []
        self.autosave = autosave

        if autosave:
            self.path = dir_path + '/' + _determine_tracker_filename(self, self.dir_path, '.csv')

    def update(self, ind_var, *dep_vars):
        """
        Update tracker's data.
        :param ind_var: a current value of the independent variable.
        :param dep_vars: current values of all dependent variables.
        """
        if len(dep_vars) != len(self.dep_var_names):
            raise Exception(f"Amount of data values ({1 + len(dep_vars)}) is "
                            f"different than the amount of data labels ({len(self.dep_var_names) + 1}).")

        curr_data = (ind_var, *dep_vars)
        self.data.append(curr_data)

        # save if autosave is enabled
        if self.autosave:
            self._append_to_out_file(','.join([str(v) for v in self.data[-1]]))

        # update the live view queue if exists
        if self.monitor.live_view_queue:
            self.monitor.live_view_queue.put((self._id, curr_data))

        # refresh monitor toggles
        _refresh_monitor_toggles(self.monitor)

    def save(self, path=None):
        """
        Save data to an output file.
        If autosave is enabled, then default output file
        is removed.
        :param path: path for the output file, otherwise, determined by
                     the data labels.
        """

        # determine output file path
        if not path:
            path = self.dir_path + '/' + _determine_tracker_filename(self, self.dir_path, '.csv')

        # write data to output file
        with open(path, 'w') as out_file:
            content = ""
            for line in self.data:
                content += ','.join([str(v) for v in line]) + '\n'
            out_file.write(content)

        # remove previous output file if existed
        if p := getattr(self, 'path', False):
            remove(p)

    def _append_to_out_file(self, line):
        try:
            with open(self.path, 'a') as out_file:
                out_file.write(line + '\n')
        except PermissionError:
            warnings.warn("Tracker's output file is denying permission."
                          "\nCheck if the file is currently open in another program."
                          "\nThe program is currently blocked until permission "
                          "is granted.")
            # wait and then try again
            time.sleep(1)
            self._append_to_out_file(line)


class Toggle:
    """
    A helper class for Monitor that represents a toggle button.
    """
    def __init__(self, main_toggle, name='Toggle', desc="Press to toggle", window_title="Toggle(s)"):
        self.toggle_count = 0

        if not main_toggle:
            self.main = True

            self.id = 0
            self.counts = Manager().list()
            self.counts.append(0)

            self.__in_q = Queue()
            self.__process = Process(target=_toggle_window, args=(self.__in_q, self.counts, name, desc, window_title,))
            self.__process.start()

        else:
            self.main = False

            self.id = len(main_toggle.counts)
            self.counts = main_toggle.counts
            self.counts.append(0)

            self.__in_q = main_toggle.__in_q
            self._send(1)  # signal to add a toggle
            self._send(name)
            self._send(desc)

    def toggled(self):
        if self.counts[self.id] > 0:
            self.toggle_count += 1
            self.counts[self.id] -= 1
            return True
        return False

    def close(self):
        self._send(2)
        self._send(self.id)

    def _send(self, data):
        self.__in_q.put(data)


# -----------------
# UTILITY FUNCTIONS
# -----------------
def _live_view_process(monitor: Monitor, data_q: Queue, update_rate):
    """
    This is the live view process.
    It creates and updates the live view figure.
    :param monitor: a monitor clone object (pickled and un-pickled).
    :param data_q: a data queue to send data to the process.
    :param update_rate: how many updates per second.
    """
    plt.ion()

    figure = None
    active = True

    # create an id_to_tracker dictionary
    id_to_tracker = dict()
    for trackers in monitor.grouped_trackers.values():
        for tracker in trackers:
            id_to_tracker[tracker._id] = tracker

    trackers = []
    id_to_axes = dict()

    while active:
        while not data_q.empty():
            # get info from queue
            if not (info := data_q.get_nowait()):  # if info is None, it's a signal to quit
                active = False
                break

            _id, data = info
            # check if id is known to the process, because
            # it could be a new id that hasn't been sent to the process in advance
            if _id in id_to_tracker:

                # update tracker data
                id_to_tracker[_id].data.append(data)

                # if new tracker
                if id_to_tracker[_id] not in trackers:
                    # add tracker to trackers
                    trackers.append(id_to_tracker[_id])

                    # redraw figure
                    figure, axs = _redraw_live_view(monitor, figure, trackers)

                    # update id_to_axes
                    for i in range(len(trackers)):
                        id_to_axes[trackers[i]._id] = axs[i]

                # if an already existing tracker
                else:
                    # update the appropriate axes
                    _update_live_view_axes(data, id_to_tracker[_id], id_to_axes[_id])

        if figure:  # update figure
            figure.canvas.draw()
            figure.canvas.flush_events()
            _custom_pause_live_view(10 ** -36)

        # wait for next update
        time.sleep(1 / update_rate)

    plt.ioff()


def _custom_pause_live_view(interval):
    backend = plt.rcParams['backend']
    if backend in matplotlib.rcsetup.interactive_bk:
        fig_manager = matplotlib._pylab_helpers.Gcf.get_active()
        if fig_manager is not None:
            canvas = fig_manager.canvas
            if canvas.figure.stale:
                canvas.draw()
            canvas.start_event_loop(interval)
            return


def _redraw_live_view(monitor, prev_figure, trackers):
    """
    In case new trackers are added to the live view,
    a new figure is created with this function.
    :param monitor: the monitor.
    :param prev_figure: the previous figure.
    :param trackers: the updated list of trackers.
    :return: new figure and a list of axes objects.
    """
    if prev_figure:
        plt.close()

    figure, axs = _monitor_plot(monitor, *trackers, return_figure_and_axs=True)
    figure.canvas.manager.set_window_title('Monitor (live-view mode)')
    plt.show(block=False)
    return figure, axs


def _update_live_view_axes(new_data, tracker, axes):
    """
    Update a live view axes according to a new data update.
    :param new_data: a tuple of new data values.
    :param tracker: a tracker that stores all the data for the axes lines.
    :param axes: the axes of the plot.
    """

    # update x and y values
    xs = [d[0] for d in tracker.data]
    i = 1
    for line in axes.get_lines():
        ys = [d[i] for d in tracker.data]
        line.set_xdata(xs)
        line.set_ydata(ys)
        i += 1

    # get x and y limits
    x_min, x_max = axes.get_xlim()
    y_min, y_max = axes.get_ylim()

    # check if new data changes x and y limits and update them
    if new_data[0] < x_min:
        x_min = new_data[0]
    elif new_data[0] > x_max:
        x_max = new_data[0]

    for v in new_data[1:]:
        if v < y_min:
            y_min = v
        elif v > y_max:
            y_max = v

    # update x and y limits
    axes.set_xlim(x_min, x_max)
    axes.set_ylim(y_min, y_max)


def _refresh_monitor_toggles(monitor):
    """
    Check if monitor's main toggles have been toggled.
    :param monitor: a monitor.
    """
    # if live view toggle toggled
    if getattr(monitor, 'live_view_toggle', False) and monitor.live_view_toggle.toggled():
        if monitor.live_view_toggle.toggle_count % 2:
            monitor.open_live_view()
        else:
            monitor.close_live_view()

    # if plot toggle toggled
    if getattr(monitor, 'plot_toggle', False) and monitor.plot_toggle.toggled():
        group_names = [group_name for group_name in monitor.grouped_trackers if group_name != "no_group"]
        monitor.plot(*group_names)


def _monitor_plot(monitor, *args, return_figure_and_axs=False):
    """
    Plot all groups or trackers in a single figure.
    :param args: either group names, or Tracker objects.
    :param return_figure_and_axs: if True, a matplotlib figure is returned
                                  instead of being displayed, along with an array of axes objects.
    :return: (optionally) a matplotlib figure, and an array of axs.
    """
    if not len(args):
        if return_figure_and_axs:
            return plt.figure(), []
        return

    # create a figure for the plot
    n_cols = min(len(args), 3)  # three plots in a row
    n_rows = len(args) // n_cols + (1 if len(args) % n_cols else 0)
    figure = plt.figure(figsize=(5, 5) if len(args) == 1 else (n_cols * 3.5, n_rows * 3.5))
    axs = figure.subplots(nrows=n_rows, ncols=n_cols,
                          squeeze=False).flatten()

    figure.tight_layout()
    figure.subplots_adjust(wspace=0.5, hspace=0.7, left=0.1, right=0.95, top=0.9, bottom=0.145)

    for i in range(len(args)):
        arg = args[i]
        ax = axs[i]

        # if arg is a string, consider it a group name
        if type(arg) == str:
            if arg not in monitor.grouped_trackers:
                raise ValueError(f"Invalid group name passed to plot()!"
                                 f"\n'{arg}' is not a group name provided to the "
                                 f"monitor.")

            title = arg
            trackers = monitor.grouped_trackers[arg]

        # else if arg is a tracker, it should have its own axes
        elif type(arg) == Tracker:
            title = f'{", ".join(arg.dep_var_names)} against {arg.ind_var_name}'
            trackers = [arg]

        # else, this is an invalid argument, raise an exception
        else:
            raise ValueError(f"Invalid argument passed to plot()!"
                             f"\nA {type(arg)} object cannot be plotted."
                             f"\nplot() accepts either a group name (str)"
                             f" or a Tracker object.")

        # plot trackers
        _plot_trackers(ax, trackers)

        # set axes title
        ax.set_title(title)

    # hide axs with no plots
    for i in range(len(args), len(axs)):
        axs[i].axis('off')

    if return_figure_and_axs:
        return figure, axs

    # else, display figure
    plt.show()


def _plot_trackers(axes, trackers):
    """
    Plot a group of trackers' data.
    :param axes: a matplotlib axes.
    :param trackers: a list of trackers.
    """
    # plot all graphs
    for tracker in trackers:
        xs = [line[0] for line in tracker.data]
        for i in range(len(tracker.dep_var_names)):
            ys = [line[i + 1] for line in tracker.data]
            axes.plot(xs, ys, label=tracker.dep_var_names[i])

    # set axis labels
    if len(trackers) == 1 and len(trackers[0].dep_var_names) == 1:
        # then there is only a single line
        axes.set_xlabel(trackers[0].ind_var_name.capitalize())
        axes.set_ylabel(trackers[0].dep_var_names[0].capitalize())

    else:
        # then there are multiple lines
        x_labels = set([tracker.ind_var_name for tracker in trackers])
        axes.set_xlabel(', '.join(x_labels).capitalize())
        axes.legend()


def _toggle_window(in_q, _counts, name, desc, window_title):
    """
    This process creates toggle buttons and listens to toggles.
    :param in_q: instruction queue.
    :param _counts: counts array-like.
    :param name: (main) toggle name.
    :param desc: (main) toggle description.
    :param window_title: a window title.
    """
    window = Tk()
    window.title(window_title)

    window.rowconfigure(0, weight=1)
    window.rowconfigure(1, weight=1)

    columns = 0
    buttons = []
    closed = []
    width = 0

    def add_button(_name, _desc):
        nonlocal columns, width

        index = columns

        def on_toggle():
            _counts[index] += 1

        window.columnconfigure(columns, weight=1)

        label = Label(window, text=_desc, font=('Ariel', 20, 'bold'))

        s = ttk.Style()
        s.configure('my.TButton', font=('Ariel', 20, 'bold'))
        btn = ttk.Button(window,
                         text=_name,
                         command=on_toggle, style='my.TButton')
        buttons.append(btn)
        closed.append(False)

        label.grid(row=0, column=columns)
        btn.grid(row=1, column=columns, sticky="NSEW", padx=20, pady=(0, 20))
        columns += 1

        width += (max(len(_desc), len(_name)) + 3) * 15
        window.geometry(f"{width}x300")

    add_button(name, desc)

    def check_signal():
        keep_listening = True

        while not in_q.empty():
            signal = in_q.get()
            if signal == 1:  # add another window
                _name = in_q.get()
                _desc = in_q.get()
                add_button(_name, _desc)
                window.geometry(f'{len(buttons) * 300}x300')

            if signal == 2:  # close a toggle
                _id = in_q.get()
                closed[_id] = True

                if all(closed):  # Then stop process
                    window.destroy()
                    keep_listening = False
                    break

                buttons[_id].state(["disabled"])

        if keep_listening:
            window.after(3000, check_signal)

    check_signal()

    window.mainloop()


def _determine_tracker_filename(tracker, dir_path, ending):
    name = '-'.join([tracker.ind_var_name] + tracker.dep_var_names) + ending
    while name in next(walk(dir_path), (None, None, []))[2]:
        name = "+" + name
    return name.replace(':', '-')


def _load_to_tracker(tracker, path):
    """
    Load a tracker object from a path.
    :param tracker: a tracker object to load the data into.
    :param path: path to data file.
    """
    with open(path, 'r') as file:
        for line in file.readlines():
            tracker.data.append(tuple([float(d) for d in line.replace('\n', '').split(',')]))


def _generate_directory(dir_name, super_directory):
    if not super_directory:
        super_directory = f'../data/{str(date.today())}'

    _create_dir_path(super_directory)

    if not dir_name:
        # determine directory name
        last_dir_num = 0

        # walk through directories of super_directory
        for dirn in next(walk(super_directory), [()] * 2)[1]:
            # if directory is empty of files, use it
            directory_content = next(walk(super_directory + f"/{dirn}"), [()] * 3)
            if len(directory_content[2]) == 0 and len(directory_content[1]) == 0:
                dir_name = dirn
                break

            # otherwise keep most recent file name (name is "S + number" like S1, S2...)
            if len(dirn) > 1 and dirn[1:].isnumeric() and (dir_num := int(dirn[1:])) > last_dir_num:
                last_dir_num = dir_num

        # if not already found a dir_name
        if not dir_name:
            dir_name = "S" + str(last_dir_num + 1)

    # build path
    dir_path = super_directory + f"/{dir_name}"

    # create directory if it doesn't exist
    _create_dir_path(dir_path)
    return dir_path


def _create_dir_path(dir_path):
    Path(dir_path).mkdir(parents=True, exist_ok=True)
