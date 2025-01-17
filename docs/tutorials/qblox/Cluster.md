---
file_format: mystnb
kernelspec:
    name: python3

---
(sec-qblox-cluster)=

# Cluster

```{code-cell} ipython3
---
mystnb:
  remove_code_source: true
---

# in the hidden cells we include some code that checks for correctness of the examples
from tempfile import TemporaryDirectory

from quantify_scheduler import Schedule
from quantify_scheduler.operations.pulse_library import SquarePulse
from quantify_scheduler.compilation import determine_absolute_timing
from quantify_scheduler.backends.qblox_backend import hardware_compile
from quantify_scheduler.resources import ClockResource

from quantify_core.data.handling import set_datadir

temp_dir = TemporaryDirectory()
set_datadir(temp_dir.name)
```

In this section we introduce how to configure [Qblox Clusters](https://www.qblox.com/cluster) and the options available for them via Quantify.
For information about their lower-level functionality, you can consult the [Qblox Instruments documentation](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/).
For information on the process of compilation to hardware, see {ref}`sec-tutorial-compiling`.

## General hardware mapping structure, example

We start by looking at an example config for a single cluster. The hardware configuration specifies which outputs are used, clock frequency properties, gains and attenuations among other properties. The general structure is that the cluster has multiple modules, and each module can use multiple portclocks.

```{code-cell} ipython3
---
mystnb:
  number_source_lines: true
  remove_code_outputs: true
---

mapping_config = {
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0": {
        "instrument_type": "Cluster",
        "ref": "internal",
        "cluster0_module1": {
            "instrument_type": "QCM",
            "complex_output_0": {
                "lo_name": "lo0",
                "portclock_configs": [
                    {
                        "clock": "q4.01",
                        "interm_freq": 200000000.0,
                        "mixer_amp_ratio": 0.9999,
                        "mixer_phase_error_deg": -4.2,
                        "port": "q4:mw",
                    },
                ]
            },
        },
        "cluster0_module2": {
            "instrument_type": "QCM_RF",
            "complex_output_0": {
                "portclock_configs": [
                    {
                        "clock": "q5.01",
                        "interm_freq": 50000000.0,
                        "port": "q5:mw"
                    }
                ]
            },
        },
    },
    "lo0": {"instrument_type": "LocalOscillator", "frequency": None, "power": 20},
}
```

```{code-cell} ipython3
---
mystnb:
  remove_code_source: true
  remove_code_outputs: true
---

# Validate mapping_config

test_sched = Schedule("test_sched")
test_sched.add(
    SquarePulse(amp=1, duration=1e-6, port="q4:mw", clock="q4.01")
)
test_sched.add(
    SquarePulse(amp=0.25, duration=1e-6, port="q5:mw", clock="q5.01")
)
test_sched.add_resource(ClockResource(name="q4.01", freq=7e9))
test_sched.add_resource(ClockResource(name="q5.01", freq=8e9))
test_sched = determine_absolute_timing(test_sched)

hardware_compile(test_sched, mapping_config)
```

Notice the {code}`"quantify_scheduler.backends.qblox_backend.hardware_compile"` backend is used. In the example, we notice that the cluster is specified using an instrument with {code}`"instrument_type": "Cluster"`. In the backend, the cluster instrument functions as a collection of modules. The modules themselves can be configured with {code}`portclock_configs`.

Also notice, that not only a cluster, but a local oscillator can also be configured with Qblox. Currently the only instrument types that can be at the top level are:
- {code}`"Cluster"`,
- {code}`"LocalOscillator"`.

## Cluster configuration

The cluster configuration must be at top level, and its `"instrument_type"` must be `"Cluster"`. The name of the cluster (the key of the structure, `"cluster0"` in the example) can be chosen freely.

It has only one required key `"ref"`, which can be `"internal"` or `"external"`. This sets the reference source, which is a 10 MHz clock source.

To add a new module mapping to the cluster, add a new key with a valid `"instrument_type"`.

### Write sequencer program to files

It is possible to optionally set `"sequence_to_file"` key to `True` or `False`. If it's not set Quantify will behave the same way as if it was set to `True`. If it is `True`, a file will be created for each sequencer with the program that's uploaded to the sequencer with the filename `<data_dir>/schedules/<year><month><day>-<hour><minute><seconds>-<milliseconds>-<random>_<port>_<clock>.json` in a JSON format, where `<random>` is 6 random characters in the range `0-9`, `a-f`.

It is possible to overwrite this parameter to `"True"` in each module configuration for each module.

```{code-block} python
---
emphasize-lines: 6
---
{
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0": {
    "instrument_type": "Cluster",
        "ref": "internal",
        "sequence_to_file": True,
        "module0": {...},
        "module1": {...},
        ...
    }
}
```

## Module configuration

For each module configuration the key must be `"<cluster_name>_module<n>"`, where `<n>` is the module number in the cluster. `"instrument_type"` is mandatory, and can be one of
- `"QCM"`,
- `"QRM"`,
- `"QCM_RF"`,
- `"QRM_RF"`.

Apart from the `"instrument_type"`, the only possible key in the module configuration for a cluster are the inputs/outputs. The possible inputs/outputs are
- for `"QCM"`: `"complex_output_{0,1}"`, `"real_output_{0,1,2,3}"`,
- for `"QRM"`: `"complex_{output,input}_0"`, `"real_{output,input}_{0,1}"`.
- for `"QCM_RF"`: `"complex_output_{0,1}"`,
- for `"QRM_RF"`: `"complex_{output,input}_0"`.

Note, for RF hardware, if an output is unused, it will be turned off. (This is to ensure that unused local oscillators do not interfere with used outputs.)

### Real mode

To use real mode, the output/input name must start with `"real_"`. When using real outputs, the backend automatically maps the signals to the correct output paths. We note that for real outputs, it is not allowed to use any pulses that have an imaginary component i.e. only real valued pulses are allowed. If you were to use a complex pulse, the backend will produce an error, e.g. square and ramp pulses are allowed but DRAG pulses not.

```{code-block} python
---
emphasize-lines: 4,12,20
---

"qcm0": {
    "instrument_type": "QCM",
    "ref": "internal",
    "real_output_0": {
        "portclock_configs": [
            {
                "port": "q0:mw",
                "clock": "q0.01",
            }
        ]
    },
    "real_output_1": {
        "portclock_configs": [
            {
                "port": "q1:mw",
                "clock": "q1.01",
            }
        ]
    },
    "real_output_2": {
        "portclock_configs": [
            {
                "port": "q2:mw",
                "clock": "q2.01",
            }
        ]
    }
},
```

### Digital mode

The markers can be controlled by defining a digital I/O, and adding a `MarkerPulse` on this I/O.
A digital I/O is defined by adding a `"digital_output_n"` to the module configuration. `n` is the number of the digital output port.
For a digital I/O only a port is required, no clocks or other parameters are needed.

```{code-block} python
"qcm0": {
    "instrument_type": "QCM",
    "ref": "internal",
    "digital_output_0": {
        "portclock_configs": [
            {
                "port": "q0:switch",
            },
        ],   
    },
},
```

The `MarkerPulse` is defined by adding a `MarkerPulse` to the sequence in question. It takes the same parameters as any other pulse.
```{code-block} python
schedule.add(MarkerPulse(duration=52e-9, port="q0:switch"))
```

### Marker configuration

The markers can be configured by adding a `"marker_debug_mode_enable"` key to I/O configurations. If the value is set to True, the operations defined for this I/O will be accompanied by a 4 ns trigger pulse on the marker located next to the I/O port.
The marker will be pulled high at the same time as the module starts playing or acquiring.
```{code-block} python
---
emphasize-lines: 2
---
"complex_output_0": {
    "marker_debug_mode_enable": True,
    ...
}
```

(sec-qblox-mixer-corrections)=
### Mixer corrections

The backend also supports setting the parameters that are used by the hardware to correct for mixer imperfections in real-time.

We configure this by adding `"dc_mixer_offset_I"` and/or `"dc_mixer_offset_Q"` to outputs, like the following example.

```{code-block} python
---
emphasize-lines: 2,3
---
"complex_output_0": {
    "dc_mixer_offset_I": -0.054,
    "dc_mixer_offset_Q": -0.034,
    ...
}
```

And you can also add `"mixer_amp_ratio"` and `"mixer_phase_error_deg"` to a specific portclock in order to set the amplitude and phase correction to correct for imperfect rejection of the unwanted sideband. See the following example.

```{code-block} python
---
emphasize-lines: 7,8
---
"complex_output_0": {
    ...
    "portclock_configs": [
        {
            "port": <port>,
            "clock": <clock>,
            "mixer_amp_ratio": 0.9997,
            "mixer_phase_error_deg": -4.0,
            ...
        }
    ]
}
```

### Gain and attenuation

For QRM, QRM-RF and QCM-RF modules you can set the gain and attenuation parameters in dB.

#### Gain configuration

* The parameters `"input_gain_I/0"` and `input_gain_Q/1` for QRM correspond to the qcodes parameters [in0_gain](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QRM.in0_gain) and [in1_gain](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QRM.in1_gain) respectively.

Note, these parameters only affect the QRM modules. For complex inputs you have to use `"input_gain_I"` and `"input_gain_Q"`, and for real inputs `"input_gain_0"` and `"input_gain_1"`.

```{code-block} python
---
emphasize-lines: 5,6,13,17
---
...
"cluster0_module1": {
    "instrument_type": "QRM",
    "complex_input_0": {
        "input_gain_I": 2,
        "input_gain_Q": 3,
        ...
    },
},
"cluster0_module2": {
    "instrument_type": "QRM",
    "real_input_0": {
        "input_gain_0": 2,
        ...
    },
    "real_input_1": {
        "input_gain_1": 3,
        ...
    },
},
```

#### Attenuation configuration

* The parameter `"complex_output_*"."output_att"` and `"complex_input_0.input_att"` for QRM-RF correspond to the qcodes parameters [out0_att](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QRM_RF.out0_att) and [in0_att](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QRM_RF.in0_att) respectively.
* The parameter `"complex_output_*"."output_att"` for QCM-RF correspond to the qcodes parameters [out0_att](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QCM_RF.out0_att) and [out1_att](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html#QCM_RF.out1_att).

Note, that these parameters only affect RF modules.

```{code-block} python
---
emphasize-lines: 5,9,16,20
---
...
"cluster0_module1": {
    "instrument_type": "QRM_RF",
    "complex_output_0": {
        "output_att": 12,
        ...
    },
    "complex_input_0": {
        "input_att": 10,
        ...
    }
},
"cluster0_module2": {
    "instrument_type": "QCM_RF",
    "complex_output_0": {
        "output_att": 4,
        ...
    },
    "complex_output_1": {
        "output_att": 6,
        ...
    },
},
```

See [Qblox Instruments: QCM-QRM](https://qblox-qblox-instruments.readthedocs-hosted.com/en/master/api_reference/qcm_qrm.html) documentation for allowed values.


### Maximum AWG output voltage

```{note}
This subsection on `max_awg_output_voltage` is still under construction.
```

(sec-qblox-clock-settings)=
### Clock settings

The aim of `quantify-scheduler` is to only specify the final RF frequency when the signal arrives at the chip, rather than any parameters related to I/Q modulation. However, you still need to provide some parameters for the up/downconversion.

The backend assumes that upconversion happens according to the relation

```{math} f_{RF} = f_{IF} + f_{LO}
```

You can specify {math}`f_{RF}` in multiple ways. You can specify it when you add a `ClockResource` with `freq` argument to your `Schedule`, or when you specify the `BasicTransmonElement.clock_freqs`.

```{note}
If you use gate level operations, you have to follow strict rules for the naming of the clock resource, for each kind of operation:
- `"<transmon name>.01"` for `Rxy` operation (and its derived operations),
- `"<transmon name>.ro"` for any measure operation,
- `"<transmon name>.12"` for the {math}`|1\rangle \rightarrow |2\rangle` transition.
```

Then,
- for baseband modules, you can optionally specify a local oscillator by its name using the `"lo_name"` key. If you specify it, the `"frequency"` key in the local oscillator specification (see the example below) specifies {math}`f_{LO}` of this local oscillator. Otherwise, {math}`f_{LO} = 0` and {math}`f_{RF} = f_{IF}`. {math}`f_{RF} = f_{IF}` can also be set in the hardware mapping explicitly with the `"interm_freq"` key in the portclock configuration.
- For RF modules, you can specify {math}`f_{IF}` inside each portclock configuration in the hardware mapping for each portclock with the `"interm_freq"` key, and/or you can specify the local oscillator for each output with the `"lo_freq"`, because they have internal local oscillators. Note, if you specify both, the relationship between these frequencies should hold, otherwise you get an error message. It's important to note, that fast frequency sweeps only work when {math}`f_{LO}` is fixed, and {math}`f_{IF}` is unspecified. Because of this, it is generally advised to specify {math}`f_{LO}` only.

In the following example for the baseband modules `"complex_output_0"`'s {math}`f_{IF}` is the same as the `"q0.01"` clock resource's frequency, and `"complex_output_1"`'s {math}`f_{IF}` is calculated using the frequency of `"lo1"` and `"q1.01"` For the RF modules, `"complex_output_0"`'s {math}`f_{IF}` is calculated using the provided `"lo_freq"` and the frequency of `"q2.01"`, and for `"complex_output_1"`, it's {math}`f_{LO}` is calculated using the provided `"interm_freq"` and the frequency of `"q3.01"`.

```{code-cell} ipython3
---
mystnb:
  remove_code_outputs: true
---

mapping_config = {
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0": {
        "instrument_type": "Cluster",
        "ref": "internal",
        "cluster0_module0": {
            "instrument_type": "QCM",
            "complex_output_0": {
                "portclock_configs": [
                    {
                        "clock": "q0.01",
                        "port": "q0:mw"
                    }
                ]
            },
            "complex_output_1": {
                "lo_name": "lo1",
                "portclock_configs": [
                    {
                        "clock": "q1.01",
                        "port": "q1:mw"
                    }
                ]
            },
        },
        "cluster0_module1": {
            "instrument_type": "QCM_RF",
            "complex_output_0": {
                "lo_freq": 7e9,
                "portclock_configs": [
                    {
                        "clock": "q2.01",
                        "port": "q2:mw"
                    }
                ]
            },
            "complex_output_1": {
                "portclock_configs": [
                    {
                        "clock": "q3.01",
                        "interm_freq": 50000000.0,
                        "port": "q3:mw"
                    }
                ]
            },
        },
    },
    "lo1": {"instrument_type": "LocalOscillator", "frequency": 5e9, "power": 20},
}

test_sched = Schedule("test_sched")
test_sched.add_resource(ClockResource(name="q0.01", freq=8e9))
test_sched.add_resource(ClockResource(name="q1.01", freq=9e9))
test_sched.add_resource(ClockResource(name="q2.01", freq=8e9))
test_sched.add_resource(ClockResource(name="q3.01", freq=9e9))

test_sched.add(SquarePulse(amp=1, duration=1e-6, port="q0:mw", clock="q0.01"))
test_sched.add(SquarePulse(amp=0.25, duration=1e-6, port="q1:mw", clock="q1.01"))
test_sched.add(SquarePulse(amp=0.25, duration=1e-6, port="q2:mw", clock="q2.01"))
test_sched.add(SquarePulse(amp=0.25, duration=1e-6, port="q3:mw", clock="q3.01"))
test_sched = determine_absolute_timing(test_sched)
hardware_compile(test_sched, mapping_config)
```

### Downconverter

```{note}
This section is only relevant for users with custom Qblox downconverter hardware.
```

Some users employ a custom Qblox downconverter module. In order to use it with this backend, we specify a {code}`"downconverter_freq"` entry in the outputs that are connected to this module, as exemplified below.

The result is that the clock frequency is downconverted such that the signal reaching the target port is at the desired clock frequency, i.e. {math}`f_\mathrm{out} = f_\mathrm{downconverter} - f_\mathrm{in}`.

For baseband modules, downconversion will not happen if `"mix_lo"` is not `True` and there is no external LO specified (`"mix_lo"` is `True` by default). For RF modules, the `"mix_lo"` setting is not used (effectively, always `True`). Also see helper function {func}`~quantify_scheduler.backends.qblox.helpers.determine_clock_lo_interm_freqs`.

```{code-block} python
---
emphasize-lines: 8,9,24
linenos: true
---

mapping_config = {
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0": {
      "cluster0_module0": {
          "instrument_type": "QCM",
          "ref": "internal",
          "complex_output_0": {
              "downconverter_freq": 9000000000,
              "mix_lo": True,
              "portclock_configs": [
                  {
                      "port": "q0:mw",
                      "clock": "q0.01",
                      "interm_freq": 50000000.0
                  }
              ]
          }
       }
    },
    "cluster0_module1": {
          "instrument_type": "QCM_RF",
          "ref": "internal",
          "complex_output_0": {
              "downconverter_freq": 9000000000,
              "portclock_configs": [
                  {
                      "port": "q0:mw",
                      "clock": "q0.01",
                      "interm_freq": 50000000.0
                  }
              ]
          }
       }
    }
}
hardware_compile(test_sched, mapping_config)

```

### Portclock configuration

Each module can have at most 6 portclocks defined, and the name for each `"port"` and `"clock"` combination must be unique. Each of these portclocks is associated with one sequencer in the Qblox hardware.

```{note}
If you use gate level operations, you have to follow strict rules for each kind of operation on which port name you can use (what's the naming convention for each port resource).
- `"<device element name>:mw"` for `Rxy` operation (and its derived operations),
- `"<device element name>:res"` for any measure operation,
- `"<device element name>:fl"` for the flux port.
```

The only required keys are the `"port"` and `"clock"` which are needed to be defined.
The following parameters are available.
- `"interm_freq"` defines the {math}`f_{IF}`, see {ref}`Clock settings <sec-qblox-clock-settings>`,
- `"mixer_amp_ratio"` by default `1.0`, must be between `0.5` and `2.0`, see {ref}`Mixer corrections <sec-qblox-mixer-corrections>`,
- `"mixer_phase_error_deg"` by default `0.0`, must be between `-45` and `45`, {ref}`Mixer corrections <sec-qblox-mixer-corrections>`,
- `"ttl_acq_threshold"`,
- `"init_offset_awg_path_0"` by default `0.0`, must be between `-1.0` and `1.0`,
- `"init_offset_awg_path_1"` by default `0.0`, must be between `-1.0` and `1.0`,
- `"init_gain_awg_path_0"` by default `1.0`, must be between `-1.0` and `1.0`,
- `"init_gain_awg_path_1"` by default `1.0`, must be between `-1.0` and `1.0`,
- `"qasm_hook_func"`, see {ref}`QASM hook <sec-qblox-qasm-hook>`,
- `"instruction_generated_pulses_enabled"`, see {ref}`Instruction generated pulses (deprecated) <sec-qblox-instruction-generated-pulses>`.

```{note}
We note that it is a requirement of the backend that each combination of a port and a clock is unique, i.e. it is possible to use the same port or clock multiple times in the hardware config but the combination of a port with a certain clock can only occur once.
```

(sec-qblox-qasm-hook)=
### QASM hook

It is possible to inject custom qasm instructions for each port-clock combination (sequencer), see the following example to insert a NOP (no operation) at the beginning of the program at line 0.

```{code-block} python
---
emphasize-lines: 17
---
def _func_for_hook_test(qasm: QASMProgram):
    qasm.instructions.insert(
        0, QASMProgram.get_instruction_as_list(q1asm_instructions.NOP)
    )

hw_config = {
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0_module1": {
          "instrument_type": "QCM_RF",
          "ref": "internal",
          "complex_output_0": {
              "downconverter_freq": 9000000000,
              "portclock_configs": [
                  {
                      "port": "q0:mw",
                      "clock": "q0.01",
                      "qasm_hook_func": _func_for_hook_test,
                  }
              ]
          }
    }
}
```

(sec-qblox-instruction-generated-pulses)=
### Instruction generated pulses

```{warning}
The {code}`instruction_generated_pulses_enabled` option is deprecated and will be removed in a future version. Long square pulses and staircase pulses can be generated with the newly introduced {class}`~quantify_scheduler.operations.stitched_pulse.StitchedPulseBuilder`. More information can be found in {ref}`Long waveform support <sec-qblox-cluster-long-waveform-support>`.
```

The Qblox backend contains some intelligence that allows it to generate certain specific waveforms from the pulse library using a more complicated series of sequencer instructions, which helps conserve waveform memory. Though in order to keep the backend fully transparent, all such advanced capabilities are disabled by default.

In order to enable the advanced capabilities we need to add line {code}`"instruction_generated_pulses_enabled": True` to the port-clock configuration.

```{code-block} python
---
  emphasize-lines: 12
---
hw_config = {
    "backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
    "cluster0_module1": {
          "instrument_type": "QCM_RF",
          "ref": "internal",
          "complex_output_0": {
              "downconverter_freq": 9000000000,
              "portclock_configs": [
                  {
                      "port": "q0:mw",
                      "clock": "q0.01",
                      "instruction_generated_pulses_enabled": True,
                  }
              ]
          }
    }
}
```

Currently, this has the following effects:

- Long square pulses get broken up into separate pulses with durations \<= 1 us, which allows the modules to play square pulses longer than the waveform memory normally allows.
- Staircase pulses are generated using offset instructions instead of using waveform memory

## Local Oscillator configuration

Local oscillator instrument can be added and then used for baseband modules. You can then reference the local oscillator instrument at the output with `"lo_name"`.

The three mandatory parameters are the `"instrument_type"` (which should be `"LocalOscillator"`), and `"frequency"` in Hz or `None`, and `"power"`.

It is also possible to add `"generic_icc_name"` as an optional parameter, but only `"generic"` is supported currently with the Qblox backend.

```{code-block} python
---
  emphasize-lines: 8,18
---
"backend": "quantify_scheduler.backends.qblox_backend.hardware_compile",
"cluster0": {
    "instrument_type": "Cluster",
    "ref": "internal",
    "cluster0_module0": {
        "instrument_type": "QCM",
        "complex_output_1": {
            "lo_name": "lo1",
            "portclock_configs": [
                {
                    "clock": "q1.01",
                    "port": "q1:mw"
                }
            ]
        },
    },
},
"lo1": {"instrument_type": "LocalOscillator", "frequency": 5e9, "power": 20},
```

## Latency corrections

Latency corrections is a `dict` containing the delays for each port-clock combination. It is possible to specify them under the key `"latency_corrections"` in the hardware config, at the top-level. See the following example.

```{code-block} python
"latency_corrections": {
    "q4:mw-q4.01": 8e-9,
    "q5:mw-q5.01": 4e-9
}
```

Each correction is in nanoseconds. For each specified port-clock, the program start will be delayed by this amount of time. Note, the delay still has to be a multiple of the grid time.

## Distortion corrections

Distortion corrections apply a function on the pulses which are in the schedule. Note, that this will not be applied to outputs generated by modifying the offset and gain/attenuation. The `"distortion_corrections"` is an optional key in the hardware config, at the top-level. See the following example.

```{code-block} python
"distortion_corrections": {
    "q0:fl-cl0.baseband": {
        "filter_func": "scipy.signal.lfilter",
        "input_var_name": "x",
        "kwargs": {
            "b": [0.0, 0.5, 1.0],
            "a": [1]
        },
        "clipping_values": [-2.5, 2.5]
    }
}
```

If `"distortion_corrections"` are set, then `"filter_func"`, `"input_var_name"` and `"kwargs"` are required. If `"clipping_values"` are set, its value must be a list with exactly 2 floats.

Clipping values are the boundaries to which the corrected pulses will be clipped,
upon exceeding, these are optional to supply.

The `"filter_func"` is a python function that we apply with `"kwargs"` arguments. The waveform to be modified will be passed to this function in the argument name specified by `"input_var_name"`. The waveform will be passed as a `np.ndarray`.

(sec-qblox-cluster-long-waveform-support)=
## Long waveform support

It is possible to play waveforms that are too long to fit in the waveform memory of Qblox modules. For a few standard waveforms, the square pulse, ramp pulse and staircase pulse, the following helper functions create operations that can readily be added to schedules:

```{code-cell} ipython3
---
mystnb:
  number_source_lines: true
  remove_code_outputs: true
---

from quantify_scheduler.operations.pulse_factories import (
    long_ramp_pulse,
    long_square_pulse,
    staircase_pulse,
)

ramp_pulse = long_ramp_pulse(amp=0.5, duration=1e-3, port="q0:mw")
square_pulse = long_square_pulse(amp=0.5, duration=1e-3, port="q0:mw")
staircase_pulse = staircase_pulse(
    start_amp=0.0, final_amp=1.0, num_steps=20, duration=1e-4, port="q0:mw"
)
```

More complex waveforms can be created from the {class}`~quantify_scheduler.operations.stitched_pulse.StitchedPulseBuilder`. This class allows you to construct complex waveforms by stitching together available pulses, and adding voltage offsets in between. Voltage offsets can be specified with or without a duration. In the latter case, the offset will hold until the last operation in the {class}`~quantify_scheduler.operations.stitched_pulse.StitchedPulse` ends. For example,

```{code-cell} ipython3
---
mystnb:
  number_source_lines: true
  remove_code_outputs: true
---

from quantify_scheduler.operations.pulse_library import RampPulse
from quantify_scheduler.operations.stitched_pulse import StitchedPulseBuilder

trapezoid_pulse = (
    StitchedPulseBuilder(port="q0:mw", clock="q0.01")
    .add_pulse(RampPulse(amp=0.5, duration=1e-8, port="q0:mw"))
    .add_voltage_offset(path_0=0.5, path_1=0.0, duration=1e-7)
    .add_pulse(RampPulse(amp=-0.5, offset=0.5, duration=1e-8, port="q0:mw"))
    .build()
)

repeat_pulse_with_offset = (
    StitchedPulseBuilder(port="q0:mw", clock="q0.01")
    .add_pulse(RampPulse(amp=0.2, duration=8e-6, port="q0:mw"))
    .add_voltage_offset(path_0=0.4, path_1=0.0)
    .add_pulse(RampPulse(amp=0.2, duration=8e-6, port="q0:mw"))
    .build()
)
```

Pulses and offsets are appended to the end of the last added operation by default. By specifying the `append=False` keyword argument in the `add_pulse` and `add_voltage_offset` methods, in combination with the `rel_time` argument, you can insert an operation at the specified time relative to the start of the {class}`~quantify_scheduler.operations.stitched_pulse.StitchedPulse`. The example below uses this to generate a series of square pulses of various durations and amplitudes.

```{code-cell} ipython3
---
mystnb:
  number_source_lines: true
  remove_code_outputs: true
---

from quantify_scheduler.operations.stitched_pulse import StitchedPulseBuilder

offsets = [0.3, 0.4, 0.5]
durations = [1e-6, 2e-6, 1e-6]
start_times = [0.0, 2e-6, 6e-6]

builder = StitchedPulseBuilder(port="q0:mw", clock="q0.01")

for offset, duration, t_start in zip(offsets, durations, start_times):
    builder.add_voltage_offset(
        path_0=offset, path_1=0.0, duration=duration, append=False, rel_time=t_start
    )

pulse = builder.build()
```
