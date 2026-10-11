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
    ARC_SEGMENT_DEGREES = 5
    FIT_PADDING = 100

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
            ("direction", "CCW"),
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
        "ArcDeg": (
            ("angle", 0),
            ("radius", 0),
            ("span_deg", 0),
            ("direction", "CCW"),
        ),
        "ArcRad": (
            ("angle", 0),
            ("radius", 0),
            ("span_radian", 0),
            ("direction", "CCW"),
        ),
        "Turn": (("angle", 0), ("distance", 0)),
        "To": (("x", 0), ("y", 0)),
        "BezierTo": (("x", 0), ("y", 0)),
        "ToShape": (("name", ""),),
    }

    def __init__(self, input_path):
        super().__init__()
        self.input_path = Path(input_path)
        self.state = State()
        self.state.shapes = State(self.load_shapes(self.input_path), deep=True)
        self.canvas_size = None
        self.view_origin = None
        self.zoom = 1.0
        self.focused_command = None
        self.focused_path_commands = None
        self.drag_action = None
        self.drag_target = None
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

                with VBox().layout(width=427):
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
                                    parameters = self.COMMAND_PARAMETERS.get(cmd[0], ())
                                    defaults = (cmd[0],) + tuple(
                                        default for _, default in parameters
                                    )
                                    with HBox():
                                        Label("cmd")
                                        with ComboBox(
                                            editable=True,
                                            text_model=cmd(0),
                                        ).layout(width=120).change(
                                            self.command_changed,
                                            cmd,
                                        ):
                                            for command_name in command_options:
                                                ComboBoxItem(command_name)

                                        for arg_idx, (arg_name, _) in enumerate(
                                            parameters,
                                            start=1,
                                        ):
                                            Label(arg_name)
                                            argument = ArgumentBinding(
                                                cmd,
                                                arg_idx,
                                                defaults,
                                            )
                                            if arg_name == "direction":
                                                with ComboBox(
                                                    text_model=argument,
                                                ).layout(width=70):
                                                    ComboBoxItem("CCW")
                                                    ComboBoxItem("CW")
                                            else:
                                                TextField(argument).layout(weight=1)

                                if (
                                    shape["commands"]
                                    and shape["commands"][0][0] in ("Path", "ClosedPath")
                                ):
                                    Button("Add Next").click(self.add_next, shape)
                            Spacer()
                    Button("Add Shape").click(self.add_shape)
                    Button("Save").click(self.save)

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
            elif command[0] in ("Path", "ClosedPath") and len(command) >= 3:
                self.draw_path(
                    canvas,
                    commands,
                    closed=command[0] == "ClosedPath",
                )

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

    @staticmethod
    def arc_direction(command, span):
        if len(command) >= 5:
            direction = str(command[4]).upper()
            if direction in ("CW", "CCW"):
                return direction
        return "CW" if span < 0 else "CCW"

    def path_geometry(self, commands, closed=False):
        try:
            current_x = float(commands[0][1])
            current_y = float(commands[0][2])
        except (IndexError, TypeError, ValueError):
            return {"points": [], "handles": []}

        start_point = (current_x, current_y)
        points = [start_point]
        handles = [
            {
                "kind": "path_start",
                "command": commands[0],
                "point": start_point,
            }
        ]
        heading = 0.0

        for command in list(commands)[1:]:
            if not command:
                continue

            command_name = command[0]
            try:
                if command_name == "To" and len(command) >= 3:
                    next_x = float(command[1])
                    next_y = float(command[2])
                    delta_x = next_x - current_x
                    delta_y = next_y - current_y
                    if delta_x or delta_y:
                        heading = math.atan2(delta_y, delta_x)
                    current_x, current_y = next_x, next_y
                    points.append((current_x, current_y))
                    handles.append(
                        {
                            "kind": "to",
                            "command": command,
                            "point": (current_x, current_y),
                        }
                    )

                elif command_name == "Turn" and len(command) >= 3:
                    origin = (current_x, current_y)
                    heading_before = heading
                    heading += math.radians(float(command[1]))
                    distance = float(command[2])
                    current_x += math.cos(heading) * distance
                    current_y += math.sin(heading) * distance
                    points.append((current_x, current_y))
                    handles.append(
                        {
                            "kind": "turn",
                            "command": command,
                            "point": (current_x, current_y),
                            "origin": origin,
                            "heading_before": heading_before,
                        }
                    )

                elif command_name in ("ArcDeg", "ArcRad") and len(command) >= 4:
                    arc_start = (current_x, current_y)
                    angle = float(command[1])
                    radius = abs(float(command[2]))
                    span = float(command[3])
                    direction = self.arc_direction(command, span)
                    if command_name == "ArcDeg":
                        angle = math.radians(angle)
                        span = math.radians(span)
                    span = abs(span) * (-1 if direction == "CW" else 1)

                    center_x = current_x - math.cos(angle) * radius
                    center_y = current_y - math.sin(angle) * radius
                    segment_count = (
                        min(
                            720,
                            max(
                                1,
                                math.ceil(
                                    abs(math.degrees(span))
                                    / self.ARC_SEGMENT_DEGREES
                                ),
                            ),
                        )
                        if radius and span
                        else 0
                    )
                    for segment_index in range(1, segment_count + 1):
                        segment_angle = angle + span * segment_index / segment_count
                        current_x = center_x + math.cos(segment_angle) * radius
                        current_y = center_y + math.sin(segment_angle) * radius
                        points.append((current_x, current_y))

                    if span:
                        heading = angle + span + (
                            math.pi / 2 if span > 0 else -math.pi / 2
                        )
                    handles.extend(
                        [
                            {
                                "kind": "arc_center",
                                "command": command,
                                "point": (center_x, center_y),
                                "start": arc_start,
                            },
                            {
                                "kind": "arc_end",
                                "command": command,
                                "point": (current_x, current_y),
                                "center": (center_x, center_y),
                                "start_angle": angle,
                            },
                        ]
                    )
            except (TypeError, ValueError):
                continue

        if closed and points[-1] != start_point:
            points.append(start_point)
        return {"points": points, "handles": handles}

    def path_points(self, commands, closed=False):
        return self.path_geometry(commands, closed=closed)["points"]

    def draw_path(self, canvas, commands, closed=False):
        geometry = self.path_geometry(commands, closed=closed)
        points = geometry["points"]
        canvas_points = [self.world_to_canvas(x, y) for x, y in points]
        focused = commands is self.focused_path_commands
        color = 0xF59E0B if focused else 0x0F766E
        if len(canvas_points) == 1:
            canvas.drawEllipse(
                *canvas_points[0],
                3,
                3,
                fill=color,
            )
        elif len(canvas_points) > 1:
            canvas.drawPolyline(canvas_points, color=color, width=2)

        if not focused:
            return

        for handle in geometry["handles"]:
            point_x, point_y = self.world_to_canvas(*handle["point"])
            if handle["kind"] == "arc_center":
                start_x, start_y = self.world_to_canvas(*handle["start"])
                canvas.drawLine(
                    start_x,
                    start_y,
                    point_x,
                    point_y,
                    color=0xFBBF24,
                )
            elif handle["kind"] == "arc_end":
                center_x, center_y = self.world_to_canvas(*handle["center"])
                canvas.drawLine(
                    center_x,
                    center_y,
                    point_x,
                    point_y,
                    color=0xFBBF24,
                )

            canvas.drawEllipse(
                point_x,
                point_y,
                self.HANDLE_RADIUS,
                self.HANDLE_RADIUS,
                fill=(
                    0xF59E0B
                    if handle["kind"] in ("path_start", "arc_center")
                    else 0xFFFFFF
                ),
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

    def path_command_lists(self):
        for shape in self.state.shapes:
            commands = shape["commands"]
            if commands and commands[0][0] in ("Path", "ClosedPath"):
                yield commands

    @staticmethod
    def point_segment_distance(point, segment_start, segment_end):
        point_x, point_y = point
        start_x, start_y = segment_start
        end_x, end_y = segment_end
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        length_squared = delta_x * delta_x + delta_y * delta_y
        if length_squared == 0:
            return math.hypot(point_x - start_x, point_y - start_y)

        fraction = max(
            0.0,
            min(
                1.0,
                ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y)
                / length_squared,
            ),
        )
        nearest_x = start_x + fraction * delta_x
        nearest_y = start_y + fraction * delta_y
        return math.hypot(point_x - nearest_x, point_y - nearest_y)

    def path_at(self, canvas_x, canvas_y):
        for commands in reversed(list(self.path_command_lists())):
            closed = commands[0][0] == "ClosedPath"
            points = [
                self.world_to_canvas(*point)
                for point in self.path_points(commands, closed=closed)
            ]
            if len(points) == 1:
                if (
                    math.hypot(canvas_x - points[0][0], canvas_y - points[0][1])
                    <= self.HANDLE_HIT_RADIUS
                ):
                    return commands
                continue

            for start, end in zip(points, points[1:]):
                if (
                    self.point_segment_distance((canvas_x, canvas_y), start, end)
                    <= self.SHAPE_HIT_MARGIN
                ):
                    return commands
        return None

    def focused_path_handle_at(self, canvas_x, canvas_y):
        if self.focused_path_commands is None:
            return None

        closed = self.focused_path_commands[0][0] == "ClosedPath"
        geometry = self.path_geometry(self.focused_path_commands, closed=closed)
        for handle in reversed(geometry["handles"]):
            handle_x, handle_y = self.world_to_canvas(*handle["point"])
            if (
                math.hypot(canvas_x - handle_x, canvas_y - handle_y)
                <= self.HANDLE_HIT_RADIUS
            ):
                return handle
        return None

    def current_path_handle(self):
        if self.focused_path_commands is None or self.drag_target is None:
            return None

        target_command, target_kind = self.drag_target
        closed = self.focused_path_commands[0][0] == "ClosedPath"
        geometry = self.path_geometry(self.focused_path_commands, closed=closed)
        for handle in geometry["handles"]:
            if handle["command"] is target_command and handle["kind"] == target_kind:
                return handle
        return None

    @staticmethod
    def signed_angle_delta(angle):
        return (angle + math.pi) % (2 * math.pi) - math.pi

    def drag_path_handle(self, world_x, world_y):
        handle = self.current_path_handle()
        if handle is None:
            return

        command = handle["command"]
        target_x = world_x + self.drag_offset[0]
        target_y = world_y + self.drag_offset[1]
        kind = handle["kind"]

        if kind in ("path_start", "to"):
            with command:
                command[1] = target_x
                command[2] = target_y
        elif kind == "turn":
            origin_x, origin_y = handle["origin"]
            delta_x = target_x - origin_x
            delta_y = target_y - origin_y
            distance = math.hypot(delta_x, delta_y)
            new_heading = (
                math.atan2(delta_y, delta_x)
                if distance
                else handle["heading_before"]
            )
            turn_angle = self.signed_angle_delta(
                new_heading - handle["heading_before"]
            )
            with command:
                command[1] = math.degrees(turn_angle)
                command[2] = distance
        elif kind == "arc_center":
            start_x, start_y = handle["start"]
            delta_x = start_x - target_x
            delta_y = start_y - target_y
            angle = math.atan2(delta_y, delta_x)
            radius = math.hypot(delta_x, delta_y)
            with command:
                command[1] = (
                    math.degrees(angle) if command[0] == "ArcDeg" else angle
                )
                command[2] = radius
        elif kind == "arc_end":
            center_x, center_y = handle["center"]
            end_angle = math.atan2(target_y - center_y, target_x - center_x)
            span = self.signed_angle_delta(end_angle - handle["start_angle"])
            old_span = float(command[3])
            direction = self.arc_direction(command, old_span)
            if direction == "CCW" and span < 0:
                span += 2 * math.pi
            elif direction == "CW" and span > 0:
                span -= 2 * math.pi
            with command:
                command[3] = (
                    math.degrees(abs(span)) if command[0] == "ArcDeg" else abs(span)
                )
                if len(command) < 5:
                    command.append(direction)

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
        self.drag_target = None
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

            path_handle = self.focused_path_handle_at(event.x, event.y)
            if path_handle is not None:
                world_x, world_y = self.canvas_to_world(event.x, event.y)
                handle_x, handle_y = path_handle["point"]
                self.drag_action = "path_handle"
                self.drag_target = (
                    path_handle["command"],
                    path_handle["kind"],
                )
                self.drag_offset = (handle_x - world_x, handle_y - world_y)
                return

            path_commands = self.path_at(event.x, event.y)
            if path_commands is not None:
                self.focused_path_commands = path_commands
                self.focused_command = None
                self.drag_action = None
                self.drag_target = None
                self.drag_position = None
                self.redraw()
                return

            command = self.circle_at(event.x, event.y)
            if command is not None:
                self.focused_command = command
                self.focused_path_commands = None
                self.drag_action = None
                self.drag_target = None
                self.drag_position = None
                self.redraw()
                return

            self.focused_command = None
            self.focused_path_commands = None

        self.drag_action = "pan"
        self.drag_target = None
        self.drag_position = (event.x, event.y)
        self.drag_offset = None
        self.redraw()

    def canvas_mouseup(self, event):
        self.drag_action = None
        self.drag_target = None
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
        elif self.drag_action == "path_handle":
            world_x, world_y = self.canvas_to_world(event.x, event.y)
            self.drag_path_handle(world_x, world_y)

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

    def drawable_bounds(self):
        bounds = []
        for shape in self.state.shapes:
            commands = shape["commands"]
            if not commands:
                continue

            command = commands[0]
            if command[0] == "Circle":
                geometry = self.circle_geometry(command)
                if geometry is not None:
                    center_x, center_y, radius = geometry
                    bounds.append(
                        (
                            center_x - radius,
                            center_y - radius,
                            center_x + radius,
                            center_y + radius,
                        )
                    )
            elif command[0] in ("Path", "ClosedPath"):
                points = self.path_points(
                    commands,
                    closed=command[0] == "ClosedPath",
                )
                if points:
                    x_values = [point[0] for point in points]
                    y_values = [point[1] for point in points]
                    bounds.append(
                        (
                            min(x_values),
                            min(y_values),
                            max(x_values),
                            max(y_values),
                        )
                    )

        if not bounds:
            return None
        return (
            min(bound[0] for bound in bounds),
            min(bound[1] for bound in bounds),
            max(bound[2] for bound in bounds),
            max(bound[3] for bound in bounds),
        )

    def fit_canvas(self, event):
        if self.canvas_size is None:
            return

        width, height = self.canvas_size
        bounds = self.drawable_bounds()
        if bounds is None:
            self.view_origin = [width / 2, height / 2]
            self.zoom = 1.0
            self.redraw()
            return

        min_x, min_y, max_x, max_y = bounds
        content_width = max_x - min_x
        content_height = max_y - min_y
        available_width = max(1, width - 2 * self.FIT_PADDING)
        available_height = max(1, height - 2 * self.FIT_PADDING)
        scale_candidates = []
        if content_width:
            scale_candidates.append(available_width / content_width)
        if content_height:
            scale_candidates.append(available_height / content_height)
        self.zoom = min(scale_candidates) if scale_candidates else 1.0
        self.zoom = min(self.MAX_ZOOM, max(self.MIN_ZOOM, self.zoom))

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        self.view_origin = [
            width / 2 - center_x * self.zoom,
            height / 2 + center_y * self.zoom,
        ]
        self.redraw()

    def add_next(self, event, shape):
        shape["commands"].append(State(["To", 0, 0], deep=True))

    def command_changed(self, event, command):
        if command is self.focused_command and command[0] != "Circle":
            self.focused_command = None
        if (
            self.focused_path_commands is not None
            and command is self.focused_path_commands[0]
            and command[0] not in ("Path", "ClosedPath")
        ):
            self.focused_path_commands = None

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

    def save(self, event):
        output_path = SaveFile(
            default=str(self.input_path),
            title="Save ShapeCmd JSON",
            types="JSON Files (*.json)|All Files (*)",
        )
        if output_path is None:
            return

        data = {"shapes": Unstate(self.state.shapes)}
        Path(output_path).write_text(
            json.dumps(data, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} INPUT.json")

    app = ShapeCmd(sys.argv[1])
    app.run()
