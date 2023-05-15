![Logo](https://raw.githubusercontent.com/roiezemel/simmon/main/assets/simmon_expanded_logo.png)

[![PyPI version](https://badge.fury.io/py/simmon.svg)](https://badge.fury.io/py/simmon)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat)](http://choosealicense.com/licenses/mit/)
[![contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](https://github.com/roiezemel/simmon)

# A simple monitor for simulations and other numeric processes

## Overview
This project provides a simple tool for tracking simulations and 
other numeric processes. It provides a Monitor class that has 
all the following functionality:
- Tracking numeric variables.
- Plotting the data.
- An updating live view of the tracked variables.
- A window of convenience toggles to control the progress
of a long-running simulation.
- Automatically saving all the collected data in a single output directory, including:
  - .csv files
  - Plots
  - A config file with configuration constants
  - A summary text file
- Loading an output directory to continue working with a simulation that's been terminated.

## Installation
Install with `pip`:
```commandline
pip install simmon
```

## Usage
Here's a quick example of the `Monitor` class used to track a moving object simulation:

```python
from simmon import Monitor

# create Monitor - this already opens an output directory and a toggle-buttons control window
mon = Monitor('Example Monitor')

# add a new 'tracker' to track variables
tr = mon.tracker('time', 'velocity')

# set simulation configuration constants
mon.its = 10000  # if declared as mon's attribute, the value will be 
mon.dt = 0.1     # added to the config.txt file
mon.a = 1

# helper variables
time = 0
v = 0

# simulate
for i in range(mon.its):
  # update tracker: provide time and velocity
  tr.update(time, v)

  # calculate next time step
  time += mon.dt
  v += mon.a * mon.dt

# finalize - saves all data and closes necessary processes and windows
mon.finalize()
```
A few notes:
- When creating a Monitor instance, an output directory is automatically created (unless disabled, see tip below).
- Also, a window of toggles opens to give the user some control over the progress of the simulation. One of the toggles 
opens the live view of the data.
- Later, a 'tracker' is added to the Monitor to track velocity against time. Each tracker is associated with **one** independent variable, 
and multiple dependent variables. When calling `update()` the number of values provided should be equal to the number of variable labels.
- Variables declared as attributes of the Monitor object (like `its` and `dt`) are considered configuration constants. These values will be
added to the config.txt file at the end.
- `finalize()` is an important method that closes all subprocesses that haven't been closed and saves all the data that hasn't been saved.

Tip: For a traceless Monitor with no output directory, use the 
QuietMonitor class instead.

### About trackers
Each 'tracker' added to the `Monitor` is provided with a sequence of data labels.
As mentioned, a 'tracker' is associated with one independent variable and multiple dependent variables:
```python
tr = mon.tracker('x', 'y1', 'y2', 'y3')  # 'y4', 'y5', ...
```
By default, the `update()` method of a tracker does not save the data into the output file.
To change that, set `autosave=` to True:
```python
tr = mon.tracker('time', 'force on body', autosave=True)
```
Sometimes, it might be helpful to give each tracker a title. This helps with the neat organization 
of the data in the output directory. Trackers with the same title are plotted on the same 
figure when `finalize()` is called. To give the tracker a title, set the `title=` keyword argument.

Use the `plot()` method of Monitor to show graphs of
the collected data.
`plot()` receives any number of arguments. Each argument can either be a 
title, a tracker object, or an iterable of tracker objects:
```python
tr1 = mon.tracker('x', 'y1', title='Things against x')
tr2 = mon.tracker('x', 'y2', title='Things against x')
tr3 = mon.tracker('time', 'force')

...

# plot everything at once:
mon.plot('Things against x', tr3, [tr1, tr2, tr3])
```

### About toggles
The 'Toggles' window is opened from the moment a Monitor is created and until `finalize()` is called.
Some toggles are added by default. Custom toggles can be added in a very simple way:

```python
from simmon import Monitor

# after this, the toggles window is opened
mon = Monitor('Custom Toggles Example')

# add a toggle button that quits the simulation
quit_toggle = mon.add_toggle(desc='Quit simulation')

...

while not quit_toggle.toggled():
# simulate stuff

...
```

As you can see, new toggles can be added very easily. The `add_toggle()` method
returns a Toggle object, whose `toggled()` method returns True for every toggle made 
by the user.


### Loading Monitor data
Finally, another cool feature of the Monitor class, is that all the data stored in 
an output directory, can later be loaded into a Monitor object. This way, a simulation 
that's been terminated can be resumed, and the data will keep streaming to the same place:

```python
from simmon import Monitor

mon = Monitor('Example Monitor')
mon.load_from_dir()  # this loads all the data from the 'Example Monitor' output directory

# now all data has been loaded back to the Monitor
print(len(mon.trackers))  # a list of all trackers
mon.plot(mon.trackers[0])  # same data can be plotted
mon.plot('Things against x')  # even the same titles
print(mon.dt, mon.its)  # config variables are still there
```

## Contributing
Please report any bug you might come across. Contributions and enhancements are very welcome!
