# quantify-scheduler

```{image} https://img.shields.io/badge/slack-chat-green.svg
:alt: Slack
:target: https://join.slack.com/t/quantify-hq/shared_invite/zt-vao45946-f_NaRc4mvYQDQE_oYB8xSw
```

```{image} https://gitlab.com/quantify-os/quantify-scheduler/badges/main/pipeline.svg
:alt: Pipelines
:target: https://gitlab.com/quantify-os/quantify-scheduler/pipelines/
```

```{image} https://img.shields.io/pypi/v/quantify-scheduler.svg
:alt: PyPi
:target: https://pypi.org/pypi/quantify-scheduler
```

```{image} https://app.codacy.com/project/badge/Grade/0c9cf5b6eb5f47ffbd2bb484d555c7e3
:alt: Code Quality
:target: https://www.codacy.com/gl/quantify-os/quantify-scheduler/dashboard?utm_source=gitlab.com&amp;utm_medium=referral&amp;utm_content=quantify-os/quantify-scheduler&amp;utm_campaign=Badge_Grade
```

```{image} https://app.codacy.com/project/badge/Coverage/0c9cf5b6eb5f47ffbd2bb484d555c7e3
:alt: Coverage
:target: https://www.codacy.com/gl/quantify-os/quantify-scheduler/dashboard?utm_source=gitlab.com&amp;utm_medium=referral&amp;utm_content=quantify-os/quantify-scheduler&amp;utm_campaign=Badge_Coverage
```

```{image} https://readthedocs.com/projects/quantify-quantify-scheduler/badge/?version=latest&token=ed6fdbf228e1369eacbeafdbad464f6de927e5dfb3a8e482ad0adcbea76fe74c
:alt: Documentation Status
:target: https://quantify-quantify-scheduler.readthedocs-hosted.com
```

```{image} https://img.shields.io/badge/License-BSD%203--Clause-blue.svg
:alt: License
:target: https://gitlab.com/quantify-os/quantify-scheduler/-/raw/main/LICENSE
```

```{image} https://img.shields.io/badge/code%20style-black-000000.svg
:alt: Code style
:target: https://github.com/psf/black
```

```{image} https://img.shields.io/badge/Supported%20By-UNITARY%20FUND-brightgreen.svg?style=flat
:alt: Unitary Fund
:target: http://unitary.fund
```

```{image} /images/QUANTIFY_LANDSCAPE.svg
:align: center
:alt: Quantify logo
```

Quantify is a python based data acquisition platform focused on Quantum Computing and solid-state physics experiments.
It is build on top of [QCoDeS](https://qcodes.github.io/Qcodes/) and is a spiritual successor of [PycQED](https://github.com/DiCarloLab-Delft/PycQED_py3).
Quantify currently consists of [quantify-core](https://pypi.org/project/quantify-core/) and [quantify-scheduler](https://pypi.org/project/quantify-scheduler/).

Take a look at the [latest documentation for quantify-scheduler](https://quantify-quantify-scheduler.readthedocs-hosted.com/) or use the switch in the bottom of left panel to read the documentation for older releases.

Quantify-scheduler is a python module for writing quantum programs featuring a hybrid gate-pulse control model with explicit timing control.
The control model allows quantum gate- and pulse-level descriptions to be combined in a clearly defined and hardware-agnostic way.
Quantify-scheduler is designed to allow experimentalists to easily define complex experiments, and produces synchronized pulse schedules to be distributed to control hardware.

```{caution}
This is a pre-release **alpha version**, major changes are expected. Use for testing & development purposes only.
```

## About

Quantify-scheduler is maintained by The Quantify consortium consisting of Qblox and Orange Quantum Systems.

```{image} https://cdn.sanity.io/images/ostxzp7d/production/f9ab429fc72aea1b31c4b2c7fab5e378b67d75c3-132x31.svg
:align: left
:target: https://qblox.com
:width: 200px
```

```{image} https://orangeqs.com/OQS_logo_with_text.svg
:align: left
:target: https://orangeqs.com
:width: 200px
```

&nbsp;

&nbsp;

The software is free to use under the conditions specified in the [license](https://gitlab.com/quantify-os/quantify-scheduler/-/raw/main/LICENSE).

% nothing-to-avoid-a-sphinx-warning: