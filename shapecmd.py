import json
import math
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
    MIN_ZOOM = 0.05
    MAX_ZOOM = 100.0
    ZOOM_STEP = 1.2
    HANDLE_RADIUS = 5
    HANDLE_HIT_RADIUS = 9
    SHAPE_HIT_MARGIN = 6

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
        self.canvas_size = None
        self.view_origin = None
        self.zoom = 1.0
        self.focused_command = None
        self.drag_action = None
        self.drag_position = None
        self.drag_offset = None
        self.cursor_position = None

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
                with VBox().layout(weight=1):
                    with HBox():
                        Button("Fit").click(self.fit_canvas)
                        Spacer()

                    (
                        Canvas(self.paint_canvas)
                        .style(bgColor=0xFFFFFF)
                        .layout(weight=1)
                        .mousedown(self.canvas_mousedown)
                        .mouseup(self.canvas_mouseup)
                        .mousemove(self.canvas_mousemove)
                        .mouseenter(self.canvas_mouseenter)
                        .mouseleave(self.canvas_mouseleave)
                        .wheel(self.canvas_wheel)
                    )

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

    def update_canvas_size(self, width, height):
        new_size = (width, height)
        if self.canvas_size is None:
            self.view_origin = [width / 2, height / 2]
        elif self.canvas_size != new_size:
            old_width, old_height = self.canvas_size
            self.view_origin[0] += (width - old_width) / 2
            self.view_origin[1] += (height - old_height) / 2
        self.canvas_size = new_size

    def canvas_to_world(self, canvas_x, canvas_y):
        origin_x, origin_y = self.view_origin
        return (
            (canvas_x - origin_x) / self.zoom,
            (origin_y - canvas_y) / self.zoom,
        )

    def world_to_canvas(self, world_x, world_y):
        origin_x, origin_y = self.view_origin
        return (
            origin_x + world_x * self.zoom,
            origin_y - world_y * self.zoom,
        )

    def draw_shapes(self, canvas):
        for shape in self.state.shapes:
            commands = shape["commands"]
            if not commands:
                continue

            command = commands[0]
            if command[0] == "Circle" and len(command) >= 4:
                self.draw_circle(canvas, command)

    @staticmethod
    def circle_geometry(command):
        try:
            return (
                float(command[1]),
                float(command[2]),
                abs(float(command[3])),
            )
        except (IndexError, TypeError, ValueError):
            return None

    def draw_circle(self, canvas, command):
        geometry = self.circle_geometry(command)
        if geometry is None:
            return

        center_x, center_y, radius = geometry
        canvas_x, canvas_y = self.world_to_canvas(center_x, center_y)
        canvas_radius = radius * self.zoom
        focused = command is self.focused_command
        stroke_color = 0xF59E0B if focused else 0x2563EB
        canvas.drawEllipse(
            canvas_x,
            canvas_y,
            canvas_radius,
            canvas_radius,
            stroke=stroke_color,
            width=2,
        )

        if focused:
            radius_x = canvas_x + canvas_radius
            canvas.drawLine(
                canvas_x,
                canvas_y,
                radius_x,
                canvas_y,
                color=0xF59E0B,
            )
            canvas.drawEllipse(
                canvas_x,
                canvas_y,
                self.HANDLE_RADIUS,
                self.HANDLE_RADIUS,
                fill=0xF59E0B,
                stroke=0xFFFFFF,
                width=1,
            )
            canvas.drawEllipse(
                radius_x,
                canvas_y,
                self.HANDLE_RADIUS,
                self.HANDLE_RADIUS,
                fill=0xFFFFFF,
                stroke=0xF59E0B,
                width=2,
            )

    def circle_commands(self):
        for shape in self.state.shapes:
            commands = shape["commands"]
            if commands and commands[0][0] == "Circle":
                yield commands[0]

    def focused_handle_at(self, canvas_x, canvas_y):
        if self.focused_command is None:
            return None

        geometry = self.circle_geometry(self.focused_command)
        if geometry is None:
            return None

        center_x, center_y, radius = geometry
        center_canvas_x, center_canvas_y = self.world_to_canvas(center_x, center_y)
        radius_canvas_x = center_canvas_x + radius * self.zoom

        if (
            math.hypot(canvas_x - center_canvas_x, canvas_y - center_canvas_y)
            <= self.HANDLE_HIT_RADIUS
        ):
            return "center"
        if (
            math.hypot(canvas_x - radius_canvas_x, canvas_y - center_canvas_y)
            <= self.HANDLE_HIT_RADIUS
        ):
            return "radius"
        return None

    def circle_at(self, canvas_x, canvas_y):
        for command in reversed(list(self.circle_commands())):
            geometry = self.circle_geometry(command)
            if geometry is None:
                continue

            center_x, center_y, radius = geometry
            center_canvas_x, center_canvas_y = self.world_to_canvas(
                center_x,
                center_y,
            )
            canvas_radius = radius * self.zoom
            if (
                math.hypot(canvas_x - center_canvas_x, canvas_y - center_canvas_y)
                <= canvas_radius + self.SHAPE_HIT_MARGIN
            ):
                return command
        return None

    def paint_canvas(self, canvas):
        self.update_canvas_size(canvas.width, canvas.height)
        origin_x, origin_y = self.view_origin
        axis_color = 0xD0D0D0
        label_color = 0x888888

        canvas.drawLine(0, origin_y, canvas.width, origin_y, color=axis_color)
        canvas.drawLine(origin_x, 0, origin_x, canvas.height, color=axis_color)

        if 0 <= origin_y < canvas.height:
            canvas.drawText(
                canvas.width - 24,
                origin_y + 4,
                "X",
                size=10,
                color=label_color,
            )
        if 0 <= origin_x < canvas.width:
            canvas.drawText(origin_x + 4, 4, "Y", size=10, color=label_color)

        self.draw_shapes(canvas)

        if self.cursor_position is not None:
            world_x, world_y = self.canvas_to_world(*self.cursor_position)
            canvas.drawText(
                12,
                12,
                f"X: {world_x:.3f}  Y: {world_y:.3f}  Zoom: {self.zoom:.3f}x",
                size=11,
                color=0x555555,
            )

    def canvas_mouseenter(self, event):
        self.cursor_position = (event.x, event.y)
        self.redraw()

    def canvas_mouseleave(self, event):
        self.cursor_position = None
        self.drag_action = None
        self.drag_position = None
        self.drag_offset = None
        self.redraw()

    def canvas_mousedown(self, event):
        if event.button not in (MouseButton.LEFT, MouseButton.MIDDLE):
            return
        self.cursor_position = (event.x, event.y)

        if self.view_origin is None:
            return

        if event.button == MouseButton.LEFT:
            handle = self.focused_handle_at(event.x, event.y)
            if handle is not None:
                geometry = self.circle_geometry(self.focused_command)
                world_x, world_y = self.canvas_to_world(event.x, event.y)
                center_x, center_y, radius = geometry
                self.drag_action = handle
                if handle == "center":
                    self.drag_offset = (center_x - world_x, center_y - world_y)
                else:
                    self.drag_offset = radius - (world_x - center_x)
                return

            command = self.circle_at(event.x, event.y)
            if command is not None:
                self.focused_command = command
                self.drag_action = None
                self.drag_position = None
                self.redraw()
                return

            self.focused_command = None

        self.drag_action = "pan"
        self.drag_position = (event.x, event.y)
        self.drag_offset = None
        self.redraw()

    def canvas_mouseup(self, event):
        self.drag_action = None
        self.drag_position = None
        self.drag_offset = None
        self.cursor_position = (event.x, event.y)
        self.redraw()

    def canvas_mousemove(self, event):
        if self.drag_action == "pan" and self.drag_position is not None:
            delta_x = event.x - self.drag_position[0]
            delta_y = event.y - self.drag_position[1]
            self.view_origin[0] += delta_x
            self.view_origin[1] += delta_y
            self.drag_position = (event.x, event.y)
        elif self.drag_action == "center" and self.focused_command is not None:
            world_x, world_y = self.canvas_to_world(event.x, event.y)
            offset_x, offset_y = self.drag_offset
            with self.focused_command:
                self.focused_command[1] = world_x + offset_x
                self.focused_command[2] = world_y + offset_y
        elif self.drag_action == "radius" and self.focused_command is not None:
            geometry = self.circle_geometry(self.focused_command)
            if geometry is not None:
                center_x, _, _ = geometry
                world_x, _ = self.canvas_to_world(event.x, event.y)
                self.focused_command[3] = max(
                    0.0,
                    world_x - center_x + self.drag_offset,
                )

        self.cursor_position = (event.x, event.y)
        self.redraw()

    def canvas_wheel(self, event):
        if not event.v_delta or self.view_origin is None:
            return

        world_x, world_y = self.canvas_to_world(event.x, event.y)
        zoom_factor = self.ZOOM_STEP ** (event.v_delta / 120)
        new_zoom = min(self.MAX_ZOOM, max(self.MIN_ZOOM, self.zoom * zoom_factor))

        self.view_origin[0] = event.x - world_x * new_zoom
        self.view_origin[1] = event.y + world_y * new_zoom
        self.zoom = new_zoom
        self.cursor_position = (event.x, event.y)
        self.redraw()

    def fit_canvas(self, event):
        if self.canvas_size is None:
            return

        width, height = self.canvas_size
        self.view_origin = [width / 2, height / 2]
        self.zoom = 1.0
        self.redraw()

    def add_next(self, event, shape):
        shape["commands"].append(State(["To", 0, 0], deep=True))

    def command_changed(self, event, command):
        if command is self.focused_command and command[0] != "Circle":
            self.focused_command = None

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
