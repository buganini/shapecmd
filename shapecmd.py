import json
import sys
from pathlib import Path

from PUI.PySide6 import *


class ArgumentBinding:
    def __init__(self, values, index, defaults):
        self.values = values
        self.index = index
        self.defaults = defaults

    @property
    def value(self):
        return self.values.get(self.index, self.defaults[self.index])

    @value.setter
    def value(self, value):
        current_value = self.values.get(self.index, self.defaults[self.index])
        converter = str if isinstance(current_value, str) else type(current_value)
        try:
            value = converter(value)
        except (TypeError, ValueError):
            return

        with self.values:
            while len(self.values) <= self.index:
                self.values.append(self.defaults[len(self.values)])
            self.values[self.index] = value


class ShapeCmd(Application):
    START_COMMANDS = (
        "Point",
        "Circle",
        "Arc",
        "Rect",
        "CenterRect",
        "RegularPolygon",
        "Path",
        "ClosedPath",
    )
    NEXT_COMMANDS = (
        "ArcDeg",
        "ArcRad",
        "Turn",
        "To",
        "BezierTo",
        "ToShape",
    )
    COMMAND_PARAMETERS = {
        "Point": (("x", 0), ("y", 0)),
        "Circle": (("center_x", 0), ("center_y", 0), ("radius", 0)),
        "Arc": (
            ("center_x", 0),
            ("center_y", 0),
            ("start_angle", 0),
            ("span_deg", 0),
        ),
        "Rect": (("x", 0), ("y", 0), ("x_offset", 0), ("y_offset", 0)),
        "CenterRect": (
            ("center_x", 0),
            ("center_y", 0),
            ("width", 0),
            ("height", 0),
        ),
        "RegularPolygon": (
            ("center_x", 0),
            ("center_y", 0),
            ("radius", 0),
            ("sides", 3),
            ("rotate_deg", 0),
        ),
        "Path": (("x", 0), ("y", 0)),
        "ClosedPath": (("x", 0), ("y", 0)),
        "ArcDeg": (("angle", 0), ("span_deg", 0)),
        "ArcRad": (("angle", 0), ("span_radian", 0)),
        "Turn": (("angle", 0), ("distance", 0)),
        "To": (("x", 0), ("y", 0)),
        "BezierTo": (("x", 0), ("y", 0)),
        "ToShape": (("name", ""),),
    }

    def __init__(self, input_path):
        super().__init__()
        self.state = State()
        self.state.shapes = State(self.load_shapes(input_path), deep=True)

    @staticmethod
    def load_shapes(input_path):
        with Path(input_path).open(encoding="utf-8") as input_file:
            data = json.load(input_file)

        if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
            raise ValueError('Input JSON must contain a "shapes" list')

        for shape in data["shapes"]:
            if not isinstance(shape, dict) or not isinstance(shape.get("commands"), list):
                raise ValueError('Each shape must contain a "commands" list')
            for command in shape["commands"]:
                if (
                    not isinstance(command, list)
                    or not command
                    or not isinstance(command[0], str)
                ):
                    raise ValueError(
                        'Each command must use the ["command", argument, ...] format'
                    )

        return data["shapes"]

    def content(self):
        with Window(title="ShapeCmd", size=(960, 640)):
            with HBox():
                Canvas(self.paint_canvas).style(bgColor=0xFFFFFF).layout(weight=1)

                with VBox().layout(width=200):
                    with Scroll():
                        with VBox():
                            for shape_idx, shape in enumerate(self.state.shapes):
                                with HBox():
                                    Label("Name")
                                    TextField(shape("name"))
                                for cmd_idx, cmd in enumerate(shape["commands"]):
                                    command_options = (
                                        self.START_COMMANDS
                                        if cmd_idx == 0
                                        else self.NEXT_COMMANDS
                                    )
                                    with ComboBox(
                                        editable=True,
                                        text_model=cmd(0),
                                    ).change(self.command_changed, cmd):
                                        for command_name in command_options:
                                            ComboBoxItem(command_name)

                                    parameters = self.COMMAND_PARAMETERS.get(cmd[0], ())
                                    defaults = (cmd[0],) + tuple(
                                        default for _, default in parameters
                                    )
                                    for arg_idx, (arg_name, _) in enumerate(
                                        parameters,
                                        start=1,
                                    ):
                                        with HBox():
                                            Label(arg_name)
                                            TextField(
                                                ArgumentBinding(
                                                    cmd,
                                                    arg_idx,
                                                    defaults,
                                                )
                                            ).layout(weight=1)

                                if (
                                    shape["commands"]
                                    and shape["commands"][0][0] in ("Path", "ClosedPath")
                                ):
                                    Button("Add Next").click(self.add_next, shape)
                            Spacer()
                    Button("Add Shape").click(self.add_shape)
                    Button("Dump").click(self.dump)

    @staticmethod
    def paint_canvas(canvas):
        """Draw the initially empty shape workspace."""

    def add_next(self, event, shape):
        shape["commands"].append(State(["To", 0, 0], deep=True))

    def command_changed(self, event, command):
        parameters = self.COMMAND_PARAMETERS.get(command[0])
        if parameters is None:
            return

        with command:
            while len(command) > 1:
                command.pop()
            for _, default in parameters:
                command.append(default)

    def add_shape(self, event):
        self.state.shapes.append(
            State(
                {"name": "", "commands": [["Point", 0, 0]]},
                deep=True,
            )
        )

    def dump(self, event):
        data = {"shapes": Unstate(self.state.shapes)}
        print(json.dumps(data, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} INPUT.json")

    app = ShapeCmd(sys.argv[1])
    app.run()
