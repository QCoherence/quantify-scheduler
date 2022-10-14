# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the main branch

from typing import Optional
from .operation import Operation


class SpectroscopyOperation(Operation):
    """Spectroscopy operation to find energy between |0> and |1> states.

    Spectroscopy operations can be supported by various qubit types, but not all of
    them. They are typically translated into a spectroscopy pulse by the quantum
    device. The frequency is taken from a clock of the device element.
    """

    def __init__(
        self,
        qubit: str,
        data: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        qubit
            The target qubit
        data
            The operation's dictionary, by default None
            Note: if the data parameter is not None all other parameters are
            overwritten using the contents of data.
        """
        if data is None:
            data = {
                "name": f"Microwave spectroscopy pulse {qubit}",
                "gate_info": {
                    "unitary": None,
                    "plot_func": "quantify_scheduler.visualization"
                    ".circuit_diagram.pulse_modulated",
                    "tex": r"Spectroscopy pulse",
                    "qubits": [qubit],
                    "operation_type": "spectroscopy_operation",
                },
            }
        super().__init__(data["name"], data=data)

    def __str__(self) -> str:
        gate_info = self.data["gate_info"]
        qubit = gate_info["qubits"][0]
        return f'{self.__class__.__name__}(qubit="{qubit}")'
