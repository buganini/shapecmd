import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import PUI

MINIMUM_PUI_VERSION = (0, 50)
installed_pui_version = tuple(int(part) for part in PUI.__version__.split("."))
if installed_pui_version < MINIMUM_PUI_VERSION:
    required_version = ".".join(str(part) for part in MINIMUM_PUI_VERSION)
    raise RuntimeError(
        f"ShapeCmd requires PUI {required_version} or newer; "
        f"found {PUI.__version__}. "
        f'Run: pip install -U "QPUIQ>={required_version}"'
    )

from PUI.PySide6 import *
from PySide6 import QtCore, QtGui, QtWidgets


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
        if isinstance(value, float):
            value = round(value, 2)

        with self.values:
            while len(self.values) <= self.index:
                self.values.append(self.defaults[len(self.values)])
            self.values[self.index] = value


class ShapeCommandTable(Table):
    ROW_HEIGHT = 26
    HORIZONTAL_SCROLLBAR_HEIGHT = 30
    FRAME_HEIGHT = 4

    def update(self, prev):
        super().update(prev)
        self.ui.setAlternatingRowColors(True)
        self.ui.setWordWrap(False)
        self.ui.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.children:
            self.ui.setColumnWidth(0, 36)
            self.ui.setColumnWidth(1, 120)
        self.ui.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        self.ui.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.ui.setFixedHeight(
            self.ROW_HEIGHT * len(self.children)
            + self.HORIZONTAL_SCROLLBAR_HEIGHT
            + self.FRAME_HEIGHT
        )


class ShapeCmd(Application):
    MIN_ZOOM = 0.05
    MAX_ZOOM = 100.0
    ZOOM_STEP = 1.2
    HANDLE_RADIUS = 5
    HANDLE_HIT_RADIUS = 9
    SHAPE_HIT_MARGIN = 6
    ARC_SEGMENT_DEGREES = 5
    BEZIER_SEGMENTS = 32
    FIT_PADDING = 100
    PATH_ARROW_SPACING = 80
    PATH_ARROW_LENGTH = 10
    PATH_ARROW_WIDTH = 8
    MAX_PATH_ARROWS = 200
    DEFAULT_RADIUS = 50
    DEFAULT_ARC_SPAN_DEGREES = 30
    DEFAULT_ARC_LENGTH = 50
    ROTATION_HANDLE_OFFSET = 20
    ARC_TO_RADIUS_HANDLE_OFFSET = 20
    SVG_PADDING = 10
    SVG_POINT_RADIUS = 2
    DIRECT_POSITION_COMMANDS = {
        "Point",
        "Circle",
        "Arc",
        "Rect",
        "CenterRect",
        "RegularPolygon",
        "Path",
        "ClosedPath",
        "To",
        "BezierTo",
        "ArcTo",
    }
    HANDLE_TOOLTIPS = {
        "center": "Center",
        "radius": "Radius",
        "point": "Position",
        "shape_center": "Center",
        "shape_radius": "Radius",
        "arc_start": "Start angle and radius",
        "shape_arc_end": "Arc span",
        "rect_origin": "Origin",
        "rect_corner": "Size",
        "center_rect_corner": "Size",
        "rect_rotation": "Rotation",
        "polygon_vertex": "Radius and rotation",
        "path_start": "Path start",
        "to": "Endpoint",
        "bezier_to": "Bezier endpoint",
        "to_shape": "Target shape position",
        "to_shape_edge": "Nearest point on target shape",
        "turn": "Turn angle and distance",
        "arc_center": "Arc center and radius",
        "arc_radius": "Arc radius",
        "arc_end": "Arc endpoint",
        "arc_to": "ArcTo endpoint",
        "arc_to_radius": "ArcTo radius",
        "segment_midpoint": "Move both endpoints",
    }

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
        "ArcDegree",
        "ArcLength",
        "ArcTo",
        "Turn",
        "To",
        "BezierTo",
        "ToShape",
        "ToShapeEdge",
    )
    COMMAND_PARAMETERS = {
        "Point": (("x", 0), ("y", 0)),
        "Circle": (
            ("center_x", 0),
            ("center_y", 0),
            ("radius", DEFAULT_RADIUS),
        ),
        "Arc": (
            ("center_x", 0),
            ("center_y", 0),
            ("radius", DEFAULT_RADIUS),
            ("start_angle", 0),
            ("span_deg", DEFAULT_ARC_SPAN_DEGREES),
            ("direction", "CCW"),
        ),
        "Rect": (
            ("x", 0),
            ("y", 0),
            ("x_offset", 0),
            ("y_offset", 0),
            ("rotate_deg", 0),
        ),
        "CenterRect": (
            ("center_x", 0),
            ("center_y", 0),
            ("width", 0),
            ("height", 0),
            ("rotate_deg", 0),
        ),
        "RegularPolygon": (
            ("center_x", 0),
            ("center_y", 0),
            ("radius", DEFAULT_RADIUS),
            ("sides", 3),
            ("rotate_deg", 0),
        ),
        "Path": (("x", 0), ("y", 0)),
        "ClosedPath": (("x", 0), ("y", 0)),
        "ArcDegree": (
            ("angle", 0),
            ("radius", DEFAULT_RADIUS),
            ("span_deg", DEFAULT_ARC_SPAN_DEGREES),
            ("direction", "CCW"),
        ),
        "ArcLength": (
            ("angle", 0),
            ("radius", DEFAULT_RADIUS),
            ("arc_length", DEFAULT_ARC_LENGTH),
            ("direction", "CCW"),
        ),
        "ArcTo": (
            ("x", 0),
            ("y", 0),
            ("radius", DEFAULT_RADIUS),
            ("direction", "CCW"),
        ),
        "Turn": (("angle", 0), ("distance", 0)),
        "To": (("x", 0), ("y", 0)),
        "BezierTo": (("x", 0), ("y", 0)),
        "ToShape": (("name", ""),),
        "ToShapeEdge": (("name", ""),),
    }

    def __init__(self, input_path):
        super().__init__()
        self.input_path = Path(input_path)
        self.state = State()
        self.state.display_arrow = True
        self.state.shapes = State(self.load_shapes(self.input_path), deep=True)
        self.state.shape_expanded = State(
            [False for _ in self.state.shapes],
            deep=True,
        )
        self.canvas_size = None
        self.view_origin = None
        self.zoom = 1.0
        self.focused_command = None
        self.focused_path_commands = None
        self.drag_action = None
        self.drag_target = None
        self.drag_position = None
        self.drag_offset = None
        self.placement_command = None
        self.placement_commands = None
        self.placement_remove_on_cancel = False
        self.cursor_position = None
        self.handle_tooltip = None
        self.normalize_all_commands()

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
                for index, value in enumerate(command[1:], start=1):
                    if isinstance(value, float):
                        command[index] = round(value, 2)

        return data["shapes"]

    @staticmethod
    def parameter_label(value):
        return "".join(part.capitalize() for part in value.split("_"))

    def normalize_all_commands(self):
        for shape in self.state.shapes:
            commands = shape.get("commands", [])
            for command in commands:
                self.normalize_command(command, commands)

    @staticmethod
    def arc_to_minimum_radius(start, target):
        radius = math.hypot(target[0] - start[0], target[1] - start[1]) / 2
        return math.ceil(radius * 100 - 1e-9) / 100

    def normalize_command(self, command, commands=None):
        if not command:
            return

        command_name = command[0]
        if command_name == "RegularPolygon" and len(command) >= 5:
            try:
                sides = max(3, min(1000, int(command[4])))
            except (TypeError, ValueError):
                sides = 3
            with command:
                command[4] = sides
            return

        if command_name != "ArcTo" or commands is None or len(command) < 4:
            return

        geometry = self.path_geometry(commands, closed=False)
        endpoint_handle = next(
            (
                handle
                for handle in geometry["handles"]
                if handle["command"] is command and handle["kind"] == "arc_to"
            ),
            None,
        )
        if endpoint_handle is None:
            return

        start_x, start_y = endpoint_handle["start"]
        target_x, target_y = endpoint_handle["point"]
        minimum_radius = self.arc_to_minimum_radius(
            (start_x, start_y),
            (target_x, target_y),
        )
        try:
            radius = abs(float(command[3]))
        except (TypeError, ValueError):
            radius = minimum_radius
        with command:
            command[3] = max(round(radius, 2), minimum_radius)

    def content(self):
        with Window(title="ShapeCmd", maximize=True).keypress(
            self.window_keypress
        ):
            with HBox():
                with VBox().layout(weight=1):
                    with HBox():
                        Button("Fit").click(self.fit_canvas)
                        Spacer()
                        Checkbox(
                            "Display Arrow",
                            self.state("display_arrow"),
                        )

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

                with VBox().layout(width=700):
                    with Scroll():
                        with VBox():
                            for shape_idx, shape in enumerate(self.state.shapes):
                                with HBox().id(f"{shape_idx}"):
                                    Label("Name")
                                    TextField(shape("name"))
                                    Button(
                                        "Hide"
                                        if self.state.shape_expanded[shape_idx]
                                        else "Show"
                                    ).click(self.toggle_shape, shape_idx)

                                if self.state.shape_expanded[shape_idx]:
                                    commands = shape["commands"]
                                    is_path = bool(
                                        commands
                                        and commands[0][0]
                                        in ("Path", "ClosedPath")
                                    )
                                    parameter_counts = [
                                        len(self.COMMAND_PARAMETERS.get(cmd[0], ()))
                                        for cmd in commands
                                    ]
                                    max_parameters = max(parameter_counts, default=0)
                                    table_height = (
                                        ShapeCommandTable.ROW_HEIGHT * len(commands)
                                        + ShapeCommandTable.HORIZONTAL_SCROLLBAR_HEIGHT
                                        + ShapeCommandTable.FRAME_HEIGHT
                                    )
                                    with (
                                        ShapeCommandTable(
                                            columnHeader=None,
                                            rowHeader=None,
                                            columnCount=2 + max_parameters,
                                        )
                                        .id(f"commands-{shape_idx}")
                                        .layout(height=table_height, weight=0)
                                    ):
                                        for cmd_idx, cmd in enumerate(commands):
                                            parameters = self.COMMAND_PARAMETERS.get(
                                                cmd[0], ()
                                            )
                                            defaults = (cmd[0],) + tuple(
                                                default for _, default in parameters
                                            )
                                            command_choices = (
                                                self.START_COMMANDS
                                                if cmd_idx == 0
                                                else self.NEXT_COMMANDS
                                            )
                                            with TableNode():
                                                TableNode(
                                                    str(cmd_idx)
                                                    if is_path and cmd_idx > 0
                                                    else ""
                                                )
                                                (
                                                    TableNode(
                                                        str(cmd[0]),
                                                        choices=command_choices,
                                                    ).set(
                                                        self.table_command_changed,
                                                        cmd,
                                                        shape,
                                                    )
                                                )
                                                for arg_idx, (
                                                    arg_name,
                                                    _,
                                                ) in enumerate(
                                                    parameters,
                                                    start=1,
                                                ):
                                                    argument = ArgumentBinding(
                                                        cmd,
                                                        arg_idx,
                                                        defaults,
                                                    )
                                                    value = argument.value
                                                    choices = (
                                                        ("CCW", "CW")
                                                        if arg_name == "direction"
                                                        else None
                                                    )
                                                    (
                                                        TableNode(
                                                            value,
                                                            display=f"{self.parameter_label(arg_name)}: {value}",
                                                            choices=choices,
                                                        ).set(
                                                            self.table_argument_changed,
                                                            argument,
                                                            cmd,
                                                            commands,
                                                        )
                                                    )

                                    if (
                                        shape["commands"]
                                        and shape["commands"][0][0]
                                        in ("Path", "ClosedPath")
                                    ):
                                        Button("Add Next").click(self.add_next, shape)
                                    Divider()
                            Spacer()
                    Button("Add Shape").click(self.add_shape)
                    with HBox():
                        Button("Save").layout(weight=1).click(self.save)
                        Button("Export SVG").layout(weight=1).click(
                            self.export_svg
                        )

    def update_canvas_size(self, width, height):
        new_size = (width, height)
        if self.canvas_size is None:
            self.canvas_size = new_size
            self.fit_view()
            return
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
            elif command[0] in (
                "Point",
                "Arc",
                "Rect",
                "CenterRect",
                "RegularPolygon",
            ):
                self.draw_standalone_shape(canvas, command)

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

    def standalone_geometry(self, command):
        try:
            command_name = command[0]
            if command_name == "Point" and len(command) >= 3:
                point = (float(command[1]), float(command[2]))
                return {
                    "points": [point],
                    "handles": [{"kind": "point", "point": point}],
                    "guides": [],
                    "closed": False,
                }

            if command_name == "Arc" and len(command) >= 6:
                center = (float(command[1]), float(command[2]))
                radius = abs(float(command[3]))
                start_angle = math.radians(float(command[4]))
                span = float(command[5])
                direction = (
                    str(command[6]).upper()
                    if len(command) >= 7
                    else ("CW" if span < 0 else "CCW")
                )
                if direction not in ("CW", "CCW"):
                    direction = "CCW"
                span = math.radians(abs(span)) * (-1 if direction == "CW" else 1)
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
                points = []
                for index in range(segment_count + 1):
                    angle = (
                        start_angle + span * index / segment_count
                        if segment_count
                        else start_angle
                    )
                    points.append(
                        (
                            center[0] + math.cos(angle) * radius,
                            center[1] + math.sin(angle) * radius,
                        )
                    )
                start = points[0]
                end = points[-1]
                radius_handle = (
                    center[0] + math.cos(start_angle) * radius / 2,
                    center[1] + math.sin(start_angle) * radius / 2,
                )
                return {
                    "points": points,
                    "handles": [
                        {"kind": "shape_center", "point": center},
                        {
                            "kind": "shape_radius",
                            "point": radius_handle,
                            "center": center,
                            "angle": start_angle,
                        },
                        {
                            "kind": "arc_start",
                            "point": start,
                            "center": center,
                        },
                        {
                            "kind": "shape_arc_end",
                            "point": end,
                            "center": center,
                            "start_angle": start_angle,
                        },
                    ],
                    "guides": [(center, start), (center, end)],
                    "closed": False,
                }

            if command_name == "Rect" and len(command) >= 5:
                origin = (float(command[1]), float(command[2]))
                x_offset = float(command[3])
                y_offset = float(command[4])
                rotation = math.radians(float(command[5])) if len(command) >= 6 else 0
                cosine = math.cos(rotation)
                sine = math.sin(rotation)

                def rect_point(local_x, local_y):
                    return (
                        origin[0] + local_x * cosine - local_y * sine,
                        origin[1] + local_x * sine + local_y * cosine,
                    )

                corner = rect_point(x_offset, y_offset)
                handle_offset = self.ROTATION_HANDLE_OFFSET / max(
                    abs(getattr(self, "zoom", 1.0)),
                    self.MIN_ZOOM,
                )
                top_y = max(0, y_offset)
                rotation_edge = rect_point(x_offset / 2, top_y)
                rotation_handle_local = (
                    x_offset / 2,
                    top_y + handle_offset,
                )
                rotation_handle = rect_point(*rotation_handle_local)
                points = [
                    origin,
                    rect_point(x_offset, 0),
                    corner,
                    rect_point(0, y_offset),
                    origin,
                ]
                return {
                    "points": points,
                    "handles": [
                        {"kind": "rect_origin", "point": origin},
                        {
                            "kind": "rect_corner",
                            "point": corner,
                            "origin": origin,
                            "rotation": rotation,
                        },
                        {
                            "kind": "rect_rotation",
                            "point": rotation_handle,
                            "pivot": origin,
                            "angle_offset": math.atan2(
                                rotation_handle_local[1],
                                rotation_handle_local[0],
                            ),
                        },
                    ],
                    "guides": [(rotation_edge, rotation_handle)],
                    "closed": True,
                }

            if command_name == "CenterRect" and len(command) >= 5:
                center = (float(command[1]), float(command[2]))
                half_width = abs(float(command[3])) / 2
                half_height = abs(float(command[4])) / 2
                rotation = math.radians(float(command[5])) if len(command) >= 6 else 0
                cosine = math.cos(rotation)
                sine = math.sin(rotation)

                def center_rect_point(local_x, local_y):
                    return (
                        center[0] + local_x * cosine - local_y * sine,
                        center[1] + local_x * sine + local_y * cosine,
                    )

                corner = center_rect_point(half_width, half_height)
                handle_offset = self.ROTATION_HANDLE_OFFSET / max(
                    abs(getattr(self, "zoom", 1.0)),
                    self.MIN_ZOOM,
                )
                rotation_edge = center_rect_point(0, half_height)
                rotation_handle = center_rect_point(0, half_height + handle_offset)
                points = [
                    center_rect_point(-half_width, -half_height),
                    center_rect_point(half_width, -half_height),
                    corner,
                    center_rect_point(-half_width, half_height),
                ]
                points.append(points[0])
                return {
                    "points": points,
                    "handles": [
                        {"kind": "shape_center", "point": center},
                        {
                            "kind": "center_rect_corner",
                            "point": corner,
                            "center": center,
                            "rotation": rotation,
                        },
                        {
                            "kind": "rect_rotation",
                            "point": rotation_handle,
                            "pivot": center,
                            "angle_offset": math.pi / 2,
                        },
                    ],
                    "guides": [
                        (center, corner),
                        (rotation_edge, rotation_handle),
                    ],
                    "closed": True,
                }

            if command_name == "RegularPolygon" and len(command) >= 6:
                center = (float(command[1]), float(command[2]))
                radius = abs(float(command[3]))
                sides = max(3, min(1000, int(command[4])))
                rotation = math.radians(float(command[5]))
                points = [
                    (
                        center[0]
                        + math.cos(rotation + 2 * math.pi * index / sides) * radius,
                        center[1]
                        + math.sin(rotation + 2 * math.pi * index / sides) * radius,
                    )
                    for index in range(sides)
                ]
                points.append(points[0])
                return {
                    "points": points,
                    "handles": [
                        {"kind": "shape_center", "point": center},
                        {
                            "kind": "polygon_vertex",
                            "point": points[0],
                            "center": center,
                        },
                    ],
                    "guides": [(center, points[0])],
                    "closed": True,
                }
        except (IndexError, TypeError, ValueError):
            return None
        return None

    def draw_standalone_shape(self, canvas, command):
        geometry = self.standalone_geometry(command)
        if geometry is None:
            return

        canvas_points = [self.world_to_canvas(*point) for point in geometry["points"]]
        focused = command is self.focused_command
        color = 0xF59E0B if focused else 0x2563EB
        if len(canvas_points) == 1:
            canvas.drawEllipse(*canvas_points[0], 3, 3, fill=color)
        elif len(canvas_points) > 1:
            canvas.drawPolyline(canvas_points, color=color, width=2)

        if not focused:
            return

        for start, end in geometry["guides"]:
            canvas.drawLine(
                *self.world_to_canvas(*start),
                *self.world_to_canvas(*end),
                color=0xFBBF24,
            )
        for handle in geometry["handles"]:
            point_x, point_y = self.world_to_canvas(*handle["point"])
            canvas.drawEllipse(
                point_x,
                point_y,
                self.HANDLE_RADIUS,
                self.HANDLE_RADIUS,
                fill=(
                    0xF59E0B
                    if handle["kind"]
                    in ("point", "shape_center", "rect_origin")
                    else 0xFFFFFF
                ),
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

    @staticmethod
    def closest_point_on_polyline(point, points):
        if not points:
            return None
        if len(points) == 1:
            return points[0]

        point_x, point_y = point
        closest = None
        closest_distance_squared = math.inf
        for start, end in zip(points, points[1:]):
            delta_x = end[0] - start[0]
            delta_y = end[1] - start[1]
            length_squared = delta_x**2 + delta_y**2
            if length_squared:
                projection = (
                    (point_x - start[0]) * delta_x
                    + (point_y - start[1]) * delta_y
                ) / length_squared
                projection = min(1.0, max(0.0, projection))
                candidate = (
                    start[0] + projection * delta_x,
                    start[1] + projection * delta_y,
                )
            else:
                candidate = start

            distance_squared = (
                (point_x - candidate[0]) ** 2 + (point_y - candidate[1]) ** 2
            )
            if distance_squared < closest_distance_squared:
                closest = candidate
                closest_distance_squared = distance_squared

        return closest

    def shape_named(self, name):
        name = str(name)
        if not name:
            return None
        return next(
            (
                shape
                for shape in self.state.shapes
                if str(shape.get("name", "")) == name
            ),
            None,
        )

    def named_shape_xy(self, name):
        target_shape = self.shape_named(name)
        if target_shape is None or not target_shape["commands"]:
            return None
        command = target_shape["commands"][0]
        try:
            return float(command[1]), float(command[2])
        except (IndexError, TypeError, ValueError):
            return None

    @staticmethod
    def translate_shape(shape, delta_x, delta_y):
        commands = shape.get("commands", [])
        if not commands or not (delta_x or delta_y):
            return

        first_command = commands[0]
        is_path = first_command and first_command[0] in ("Path", "ClosedPath")
        translated_commands = (
            [
                command
                for index, command in enumerate(commands)
                if index == 0
                or (command and command[0] in ("To", "BezierTo", "ArcTo"))
            ]
            if is_path
            else [first_command]
        )

        for command in translated_commands:
            if len(command) < 3:
                continue
            try:
                translated_x = round(float(command[1]) + delta_x, 2)
                translated_y = round(float(command[2]) + delta_y, 2)
            except (TypeError, ValueError):
                continue
            with command:
                command[1] = translated_x
                command[2] = translated_y

    def closest_point_on_named_shape(self, point, name, resolving):
        target_shape = self.shape_named(name)
        if target_shape is None or not target_shape["commands"]:
            return None

        commands = target_shape["commands"]
        command = commands[0]
        if not command:
            return None

        if command[0] == "Point" and len(command) >= 3:
            try:
                return float(command[1]), float(command[2])
            except (TypeError, ValueError):
                return None

        if command[0] == "Circle":
            geometry = self.circle_geometry(command)
            if geometry is None:
                return None
            center_x, center_y, radius = geometry
            delta_x = point[0] - center_x
            delta_y = point[1] - center_y
            distance = math.hypot(delta_x, delta_y)
            if not distance:
                return center_x + radius, center_y
            scale = radius / distance
            return center_x + delta_x * scale, center_y + delta_y * scale

        if command[0] in ("Path", "ClosedPath"):
            geometry = self.path_geometry(
                commands,
                closed=command[0] == "ClosedPath",
                resolving=resolving,
            )
            return self.closest_point_on_polyline(point, geometry["points"])

        geometry = self.standalone_geometry(command)
        if geometry is not None:
            return self.closest_point_on_polyline(point, geometry["points"])

        return None

    @staticmethod
    def polyline_midpoint(points):
        segments = []
        total_length = 0.0
        for start, end in zip(points, points[1:]):
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            segments.append((start, end, length))
            total_length += length

        if not segments:
            return points[0] if points else None
        if not total_length:
            return segments[0][0]

        target = total_length / 2
        offset = 0.0
        for start, end, length in segments:
            if offset + length >= target:
                fraction = (target - offset) / length if length else 0
                return (
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                )
            offset += length
        return segments[-1][1]

    def path_geometry(self, commands, closed=False, resolving=None):
        resolving = set() if resolving is None else set(resolving)
        commands_identity = id(commands)
        if commands_identity in resolving:
            return {"points": [], "handles": []}
        resolving.add(commands_identity)

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
        previous_endpoint_handle = handles[0]
        heading = 0.0

        for endpoint_index, command in enumerate(list(commands)[1:], start=1):
            if not command:
                continue

            command_name = command[0]
            segment_start_index = len(points) - 1
            handle_start_index = len(handles)
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

                elif command_name == "BezierTo" and len(command) >= 3:
                    start_x, start_y = current_x, current_y
                    next_x = float(command[1])
                    next_y = float(command[2])
                    delta_x = next_x - start_x
                    delta_y = next_y - start_y
                    distance = math.hypot(delta_x, delta_y)

                    if distance:
                        control_distance = distance / 3
                        control1_x = (
                            start_x + math.cos(heading) * control_distance
                        )
                        control1_y = (
                            start_y + math.sin(heading) * control_distance
                        )
                        end_heading = math.atan2(delta_y, delta_x)
                        control2_x = (
                            next_x - math.cos(end_heading) * control_distance
                        )
                        control2_y = (
                            next_y - math.sin(end_heading) * control_distance
                        )

                        for segment_index in range(1, self.BEZIER_SEGMENTS + 1):
                            t = segment_index / self.BEZIER_SEGMENTS
                            inverse_t = 1 - t
                            current_x = (
                                inverse_t**3 * start_x
                                + 3 * inverse_t**2 * t * control1_x
                                + 3 * inverse_t * t**2 * control2_x
                                + t**3 * next_x
                            )
                            current_y = (
                                inverse_t**3 * start_y
                                + 3 * inverse_t**2 * t * control1_y
                                + 3 * inverse_t * t**2 * control2_y
                                + t**3 * next_y
                            )
                            points.append((current_x, current_y))

                        heading = end_heading
                    else:
                        current_x, current_y = next_x, next_y

                    handles.append(
                        {
                            "kind": "bezier_to",
                            "command": command,
                            "point": (current_x, current_y),
                        }
                    )

                elif (
                    command_name in ("ToShape", "ToShapeEdge")
                    and len(command) >= 2
                ):
                    if command_name == "ToShape":
                        next_point = self.named_shape_xy(command[1])
                    else:
                        next_point = self.closest_point_on_named_shape(
                            (current_x, current_y),
                            command[1],
                            resolving,
                        )
                    if next_point is None:
                        continue

                    next_x, next_y = next_point
                    delta_x = next_x - current_x
                    delta_y = next_y - current_y
                    if delta_x or delta_y:
                        heading = math.atan2(delta_y, delta_x)
                    current_x, current_y = next_x, next_y
                    points.append((current_x, current_y))
                    handles.append(
                        {
                            "kind": (
                                "to_shape"
                                if command_name == "ToShape"
                                else "to_shape_edge"
                            ),
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

                elif command_name == "ArcTo" and len(command) >= 4:
                    arc_start = (current_x, current_y)
                    next_x = float(command[1])
                    next_y = float(command[2])
                    chord_x = next_x - current_x
                    chord_y = next_y - current_y
                    chord_length = math.hypot(chord_x, chord_y)
                    radius = max(abs(float(command[3])), chord_length / 2)
                    direction = (
                        str(command[4]).upper() if len(command) >= 5 else "CCW"
                    )
                    if direction not in ("CW", "CCW"):
                        direction = "CCW"

                    if chord_length:
                        half_chord = chord_length / 2
                        normal_x = -chord_y / chord_length
                        normal_y = chord_x / chord_length
                        direction_sign = 1 if direction == "CCW" else -1
                        center_distance = direction_sign * math.sqrt(
                            max(0, radius * radius - half_chord * half_chord)
                        )
                        chord_mid_x = (current_x + next_x) / 2
                        chord_mid_y = (current_y + next_y) / 2
                        center_x = chord_mid_x + normal_x * center_distance
                        center_y = chord_mid_y + normal_y * center_distance
                        start_angle = math.atan2(
                            current_y - center_y,
                            current_x - center_x,
                        )
                        end_angle = math.atan2(
                            next_y - center_y,
                            next_x - center_x,
                        )
                        if direction == "CW":
                            span = -((start_angle - end_angle) % (2 * math.pi))
                        else:
                            span = (end_angle - start_angle) % (2 * math.pi)
                        segment_count = min(
                            720,
                            max(
                                1,
                                math.ceil(
                                    abs(math.degrees(span))
                                    / self.ARC_SEGMENT_DEGREES
                                ),
                            ),
                        )
                        for segment_index in range(1, segment_count + 1):
                            segment_angle = (
                                start_angle
                                + span * segment_index / segment_count
                            )
                            current_x = center_x + math.cos(segment_angle) * radius
                            current_y = center_y + math.sin(segment_angle) * radius
                            points.append((current_x, current_y))
                        current_x, current_y = next_x, next_y
                        points[-1] = (current_x, current_y)

                        heading = end_angle + (
                            math.pi / 2 if direction == "CCW" else -math.pi / 2
                        )
                        arc_mid_angle = start_angle + span / 2
                        arc_midpoint = (
                            center_x + math.cos(arc_mid_angle) * radius,
                            center_y + math.sin(arc_mid_angle) * radius,
                        )
                        handle_offset = self.ARC_TO_RADIUS_HANDLE_OFFSET / max(
                            abs(getattr(self, "zoom", 1.0)),
                            self.MIN_ZOOM,
                        )
                        radial_unit_x = (arc_midpoint[0] - center_x) / radius
                        radial_unit_y = (arc_midpoint[1] - center_y) / radius
                        handles.append(
                            {
                                "kind": "arc_to_radius",
                                "command": command,
                                "point": (
                                    arc_midpoint[0]
                                    - radial_unit_x * handle_offset,
                                    arc_midpoint[1]
                                    - radial_unit_y * handle_offset,
                                ),
                                "start": arc_start,
                                "target": (next_x, next_y),
                                "center": (center_x, center_y),
                                "midpoint": arc_midpoint,
                                "handle_offset": handle_offset,
                                "direction": direction,
                            }
                        )
                    else:
                        current_x, current_y = next_x, next_y

                    handles.append(
                        {
                            "kind": "arc_to",
                            "command": command,
                            "point": (current_x, current_y),
                            "start": arc_start,
                        }
                    )

                elif command_name in ("ArcDegree", "ArcLength") and len(command) >= 4:
                    arc_start = (current_x, current_y)
                    angle = float(command[1])
                    radius = abs(float(command[2]))
                    span = float(command[3])
                    direction = self.arc_direction(command, span)
                    angle = math.radians(angle)
                    if command_name == "ArcDegree":
                        span = math.radians(span)
                    else:
                        span = span / radius if radius else 0
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
                                "kind": "arc_radius",
                                "command": command,
                                "point": (
                                    (arc_start[0] + center_x) / 2,
                                    (arc_start[1] + center_y) / 2,
                                ),
                                "start": arc_start,
                                "angle": angle,
                            },
                            {
                                "kind": "arc_end",
                                "command": command,
                                "point": (current_x, current_y),
                                "start": arc_start,
                                "center": (center_x, center_y),
                                "start_angle": angle,
                                "span": span,
                            },
                        ]
                    )
            except (TypeError, ValueError):
                continue

            for handle in handles[handle_start_index:]:
                handle["endpoint_index"] = endpoint_index

            endpoint_handle = next(
                (
                    handle
                    for handle in reversed(handles[handle_start_index:])
                    if handle["kind"]
                    in {
                        "to",
                        "bezier_to",
                        "to_shape",
                        "to_shape_edge",
                        "turn",
                        "arc_to",
                        "arc_end",
                    }
                ),
                None,
            )
            if endpoint_handle is None:
                continue

            midpoint = self.polyline_midpoint(points[segment_start_index:])
            if midpoint is not None:
                handles.append(
                    {
                        "kind": "segment_midpoint",
                        "command": command,
                        "point": midpoint,
                        "start_handle": previous_endpoint_handle,
                        "end_handle": endpoint_handle,
                        "endpoint_indices": (
                            previous_endpoint_handle.get("endpoint_index"),
                            endpoint_index,
                        ),
                    }
                )
            previous_endpoint_handle = endpoint_handle

        if closed and points[-1] != start_point:
            midpoint = self.polyline_midpoint([points[-1], start_point])
            points.append(start_point)
            handles.append(
                {
                    "kind": "segment_midpoint",
                    "command": commands[0],
                    "point": midpoint,
                    "start_handle": previous_endpoint_handle,
                    "end_handle": handles[0],
                    "endpoint_indices": (
                        previous_endpoint_handle.get("endpoint_index"),
                        None,
                    ),
                }
            )
        return {"points": points, "handles": handles}

    def path_points(self, commands, closed=False):
        return self.path_geometry(commands, closed=closed)["points"]

    def draw_path_direction_arrows(self, canvas, points, color):
        segments = []
        total_length = 0.0
        for start, end in zip(points, points[1:]):
            delta_x = end[0] - start[0]
            delta_y = end[1] - start[1]
            length = math.hypot(delta_x, delta_y)
            if not length:
                continue
            segments.append((start, delta_x, delta_y, length, total_length))
            total_length += length

        if not segments:
            return

        arrow_count = max(
            1,
            min(self.MAX_PATH_ARROWS, int(total_length / self.PATH_ARROW_SPACING)),
        )
        arrow_step = total_length / arrow_count
        targets = [(index + 0.5) * arrow_step for index in range(arrow_count)]
        segment_index = 0

        for target in targets:
            while (
                segment_index + 1 < len(segments)
                and target
                > segments[segment_index][4] + segments[segment_index][3]
            ):
                segment_index += 1

            start, delta_x, delta_y, length, offset = segments[segment_index]
            distance = target - offset
            unit_x = delta_x / length
            unit_y = delta_y / length
            center_x = start[0] + unit_x * distance
            center_y = start[1] + unit_y * distance
            half_length = self.PATH_ARROW_LENGTH / 2
            half_width = self.PATH_ARROW_WIDTH / 2
            tip_x = center_x + unit_x * half_length
            tip_y = center_y + unit_y * half_length
            back_x = center_x - unit_x * half_length
            back_y = center_y - unit_y * half_length
            perpendicular_x = -unit_y
            perpendicular_y = unit_x

            canvas.drawLine(
                tip_x,
                tip_y,
                back_x + perpendicular_x * half_width,
                back_y + perpendicular_y * half_width,
                color=color,
                width=2,
            )
            canvas.drawLine(
                tip_x,
                tip_y,
                back_x - perpendicular_x * half_width,
                back_y - perpendicular_y * half_width,
                color=color,
                width=2,
            )

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

        if self.state.display_arrow:
            self.draw_path_direction_arrows(canvas, canvas_points, color)

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
            elif handle["kind"] == "arc_to_radius":
                midpoint_x, midpoint_y = self.world_to_canvas(
                    *handle["midpoint"]
                )
                canvas.drawLine(
                    midpoint_x,
                    midpoint_y,
                    point_x,
                    point_y,
                    color=0xFBBF24,
                )

            if handle["kind"] == "segment_midpoint":
                canvas.drawRect(
                    point_x - self.HANDLE_RADIUS,
                    point_y - self.HANDLE_RADIUS,
                    point_x + self.HANDLE_RADIUS,
                    point_y + self.HANDLE_RADIUS,
                    fill=0xF59E0B,
                )
            else:
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
        if self.focused_command is None or self.focused_command[0] != "Circle":
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

    def standalone_commands(self):
        command_names = {"Point", "Arc", "Rect", "CenterRect", "RegularPolygon"}
        for shape in self.state.shapes:
            commands = shape["commands"]
            if commands and commands[0][0] in command_names:
                yield commands[0]

    @staticmethod
    def point_in_polygon(point, polygon):
        point_x, point_y = point
        inside = False
        for start, end in zip(polygon, polygon[1:]):
            if (start[1] > point_y) == (end[1] > point_y):
                continue
            crossing_x = (
                (end[0] - start[0])
                * (point_y - start[1])
                / (end[1] - start[1])
                + start[0]
            )
            if point_x < crossing_x:
                inside = not inside
        return inside

    def standalone_at(self, canvas_x, canvas_y):
        for command in reversed(list(self.standalone_commands())):
            geometry = self.standalone_geometry(command)
            if geometry is None:
                continue
            points = [self.world_to_canvas(*point) for point in geometry["points"]]
            if len(points) == 1:
                if (
                    math.hypot(canvas_x - points[0][0], canvas_y - points[0][1])
                    <= self.HANDLE_HIT_RADIUS
                ):
                    return command
                continue
            if geometry["closed"] and self.point_in_polygon(
                (canvas_x, canvas_y), points
            ):
                return command
            for start, end in zip(points, points[1:]):
                if (
                    self.point_segment_distance((canvas_x, canvas_y), start, end)
                    <= self.SHAPE_HIT_MARGIN
                ):
                    return command
        return None

    def focused_standalone_handle_at(self, canvas_x, canvas_y):
        if self.focused_command is None or self.focused_command[0] == "Circle":
            return None
        geometry = self.standalone_geometry(self.focused_command)
        if geometry is None:
            return None
        for handle in reversed(geometry["handles"]):
            handle_x, handle_y = self.world_to_canvas(*handle["point"])
            if (
                math.hypot(canvas_x - handle_x, canvas_y - handle_y)
                <= self.HANDLE_HIT_RADIUS
            ):
                return handle
        return None

    def current_standalone_handle(self):
        if self.focused_command is None or self.drag_target is None:
            return None
        geometry = self.standalone_geometry(self.focused_command)
        if geometry is None:
            return None
        for handle in geometry["handles"]:
            if handle["kind"] == self.drag_target:
                return handle
        return None

    def drag_standalone_handle(self, world_x, world_y):
        handle = self.current_standalone_handle()
        if handle is None:
            return
        command = self.focused_command
        target_x = world_x + self.drag_offset[0]
        target_y = world_y + self.drag_offset[1]
        kind = handle["kind"]

        with command:
            if kind == "point":
                command[1] = round(target_x, 2)
                command[2] = round(target_y, 2)
            elif kind == "shape_center":
                command[1] = round(target_x, 2)
                command[2] = round(target_y, 2)
            elif kind == "arc_start":
                center_x, center_y = handle["center"]
                delta_x = target_x - center_x
                delta_y = target_y - center_y
                command[3] = round(math.hypot(delta_x, delta_y), 2)
                command[4] = round(math.degrees(math.atan2(delta_y, delta_x)), 2)
            elif kind == "shape_radius":
                center_x, center_y = handle["center"]
                direction_x = math.cos(handle["angle"])
                direction_y = math.sin(handle["angle"])
                projected_half_radius = (
                    (target_x - center_x) * direction_x
                    + (target_y - center_y) * direction_y
                )
                command[3] = round(max(0, projected_half_radius * 2), 2)
            elif kind == "shape_arc_end":
                center_x, center_y = handle["center"]
                end_angle = math.atan2(target_y - center_y, target_x - center_x)
                span = self.signed_angle_delta(end_angle - handle["start_angle"])
                direction = (
                    str(command[6]).upper() if len(command) >= 7 else "CCW"
                )
                if direction == "CCW" and span < 0:
                    span += 2 * math.pi
                elif direction == "CW" and span > 0:
                    span -= 2 * math.pi
                command[5] = round(math.degrees(abs(span)), 2)
            elif kind == "rect_origin":
                command[1] = round(target_x, 2)
                command[2] = round(target_y, 2)
            elif kind == "rect_corner":
                origin_x, origin_y = handle["origin"]
                delta_x = target_x - origin_x
                delta_y = target_y - origin_y
                cosine = math.cos(handle["rotation"])
                sine = math.sin(handle["rotation"])
                command[3] = round(delta_x * cosine + delta_y * sine, 2)
                command[4] = round(-delta_x * sine + delta_y * cosine, 2)
            elif kind == "center_rect_corner":
                center_x, center_y = handle["center"]
                delta_x = target_x - center_x
                delta_y = target_y - center_y
                cosine = math.cos(handle["rotation"])
                sine = math.sin(handle["rotation"])
                local_x = delta_x * cosine + delta_y * sine
                local_y = -delta_x * sine + delta_y * cosine
                command[3] = round(abs(local_x) * 2, 2)
                command[4] = round(abs(local_y) * 2, 2)
            elif kind == "rect_rotation":
                pivot_x, pivot_y = handle["pivot"]
                rotation = math.degrees(
                    self.signed_angle_delta(
                        math.atan2(target_y - pivot_y, target_x - pivot_x)
                        - handle["angle_offset"]
                    )
                )
                while len(command) <= 5:
                    command.append(0)
                command[5] = round(rotation, 2)
            elif kind == "polygon_vertex":
                center_x, center_y = handle["center"]
                delta_x = target_x - center_x
                delta_y = target_y - center_y
                command[3] = round(math.hypot(delta_x, delta_y), 2)
                command[5] = round(math.degrees(math.atan2(delta_y, delta_x)), 2)

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

    def move_path_endpoint_to(self, handle, target_x, target_y):
        command = handle["command"]
        kind = handle["kind"]

        if kind in ("path_start", "to", "bezier_to", "arc_to"):
            with command:
                command[1] = round(target_x, 2)
                command[2] = round(target_y, 2)
            if kind == "arc_to":
                self.normalize_command(command, self.focused_path_commands)
            return

        if kind == "turn":
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
                command[1] = round(math.degrees(turn_angle), 2)
                command[2] = round(distance, 2)
            return

        if kind != "arc_end":
            return

        start_x, start_y = handle["start"]
        chord_x = target_x - start_x
        chord_y = target_y - start_y
        chord_length = math.hypot(chord_x, chord_y)
        span = handle["span"]
        half_span_sine = abs(math.sin(span / 2))
        if chord_length <= 1e-9 or half_span_sine <= 1e-9:
            return

        radius = chord_length / (2 * half_span_sine)
        chord_angle = math.atan2(chord_y, chord_x)
        start_angle = chord_angle - span / 2 - math.copysign(math.pi / 2, span)
        with command:
            command[1] = round(math.degrees(start_angle), 2)
            command[2] = round(radius, 2)
            if command[0] == "ArcLength":
                command[3] = round(abs(span) * radius, 2)

    def translate_path_endpoint(self, handle, delta_x, delta_y, moved_shapes):
        kind = handle["kind"]
        command = handle["command"]
        if kind in ("to_shape", "to_shape_edge"):
            shape_name = str(command[1])
            if shape_name in moved_shapes:
                return
            target_shape = self.shape_named(shape_name)
            if target_shape is not None:
                self.translate_shape(target_shape, delta_x, delta_y)
                moved_shapes.add(shape_name)
            return

        self.move_path_endpoint_to(
            handle,
            handle["point"][0] + delta_x,
            handle["point"][1] + delta_y,
        )

    def drag_path_segment_midpoint(self, handle, target_x, target_y):
        delta_x = target_x - handle["point"][0]
        delta_y = target_y - handle["point"][1]
        if not delta_x and not delta_y:
            return

        desired_end = (
            handle["end_handle"]["point"][0] + delta_x,
            handle["end_handle"]["point"][1] + delta_y,
        )
        moved_shapes = set()
        self.translate_path_endpoint(
            handle["start_handle"],
            delta_x,
            delta_y,
            moved_shapes,
        )

        closed = self.focused_path_commands[0][0] == "ClosedPath"
        geometry = self.path_geometry(self.focused_path_commands, closed=closed)
        updated_handle = next(
            (
                candidate
                for candidate in geometry["handles"]
                if candidate["command"] is handle["command"]
                and candidate["kind"] == "segment_midpoint"
            ),
            None,
        )
        if updated_handle is None:
            return

        end_handle = updated_handle["end_handle"]
        if end_handle["kind"] in ("to_shape", "to_shape_edge"):
            self.translate_path_endpoint(
                end_handle,
                delta_x,
                delta_y,
                moved_shapes,
            )
        else:
            self.move_path_endpoint_to(end_handle, *desired_end)

    def drag_path_handle(self, world_x, world_y):
        handle = self.current_path_handle()
        if handle is None:
            return

        command = handle["command"]
        target_x = world_x + self.drag_offset[0]
        target_y = world_y + self.drag_offset[1]
        kind = handle["kind"]

        if kind == "segment_midpoint":
            self.drag_path_segment_midpoint(handle, target_x, target_y)
        elif kind in ("to_shape", "to_shape_edge"):
            target_shape = self.shape_named(command[1])
            if target_shape is None or self.drag_position is None:
                return
            delta_x = world_x - self.drag_position[0]
            delta_y = world_y - self.drag_position[1]
            self.translate_shape(target_shape, delta_x, delta_y)
            self.drag_position = (world_x, world_y)
        elif kind in ("path_start", "to", "bezier_to", "arc_to"):
            self.move_path_endpoint_to(handle, target_x, target_y)
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
                command[1] = round(math.degrees(turn_angle), 2)
                command[2] = round(distance, 2)
        elif kind == "arc_center":
            start_x, start_y = handle["start"]
            delta_x = start_x - target_x
            delta_y = start_y - target_y
            angle = math.atan2(delta_y, delta_x)
            radius = math.hypot(delta_x, delta_y)
            with command:
                command[1] = round(math.degrees(angle), 2)
                command[2] = round(radius, 2)
        elif kind == "arc_radius":
            start_x, start_y = handle["start"]
            direction_x = -math.cos(handle["angle"])
            direction_y = -math.sin(handle["angle"])
            projected_half_radius = (
                (target_x - start_x) * direction_x
                + (target_y - start_y) * direction_y
            )
            with command:
                command[2] = round(max(0, projected_half_radius * 2), 2)
        elif kind == "arc_to_radius":
            self.drag_arc_to_radius(handle, target_x, target_y)
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
                command[3] = round(
                    math.degrees(abs(span))
                    if command[0] == "ArcDegree"
                    else abs(span) * abs(float(command[2])),
                    2,
                )
                if len(command) < 5:
                    command.append(direction)

    def drag_arc_to_radius(self, handle, target_x, target_y):
        start_x, start_y = handle["start"]
        end_x, end_y = handle["target"]
        chord_x = end_x - start_x
        chord_y = end_y - start_y
        chord_length = math.hypot(chord_x, chord_y)
        if chord_length <= 1e-9:
            return

        half_chord = chord_length / 2
        normal_x = -chord_y / chord_length
        normal_y = chord_x / chord_length
        chord_mid_x = (start_x + end_x) / 2
        chord_mid_y = (start_y + end_y) / 2
        direction_sign = 1 if handle["direction"] == "CCW" else -1
        handle_distance = (
            (target_x - chord_mid_x) * normal_x
            + (target_y - chord_mid_y) * normal_y
        )
        sagitta = handle["handle_offset"] - direction_sign * handle_distance
        minimum_sagitta = max(1e-6, half_chord * 1e-6)
        sagitta = min(half_chord, max(minimum_sagitta, sagitta))
        radius = (
            half_chord * half_chord + sagitta * sagitta
        ) / (2 * sagitta)

        command = handle["command"]
        with command:
            command[3] = round(radius, 2)
        self.normalize_command(command, self.focused_path_commands)

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
                f"X: {world_x:.2f}  Y: {world_y:.2f}  Zoom: {self.zoom:.3f}x",
                size=11,
                color=0x555555,
            )

        if self.placement_command is not None:
            canvas.drawText(
                max(12, canvas.width / 2 - 48),
                12,
                "Esc to cancel",
                size=11,
                color=0x555555,
            )

        self.draw_handle_tooltip(canvas)

    def draw_handle_tooltip(self, canvas):
        if self.handle_tooltip is None:
            return

        text, cursor_x, cursor_y = self.handle_tooltip
        font = canvas.qpainter.font()
        font.setPointSize(12)
        metrics = QtGui.QFontMetrics(font)
        padding_x = 5
        padding_y = 3
        width = metrics.horizontalAdvance(text) + padding_x * 2
        height = metrics.height() + padding_y * 2
        left = cursor_x + 12
        top = cursor_y + 16

        if left + width > canvas.width - 4:
            left = cursor_x - width - 12
        if top + height > canvas.height - 4:
            top = cursor_y - height - 12
        left = max(4, left)
        top = max(4, top)

        canvas.drawRect(
            left,
            top,
            left + width,
            top + height,
            fill=0x242424,
            stroke=0x606060,
            width=1,
        )
        canvas.drawText(
            left + padding_x,
            top + padding_y,
            text,
            w=width - padding_x * 2,
            h=height - padding_y * 2,
            size=12,
            color=0xFFFFFF,
        )

    def canvas_mouseenter(self, event):
        self.cursor_position = (event.x, event.y)
        self.move_placement_to_canvas(event.x, event.y)
        self.update_handle_tooltip(event.x, event.y)
        self.redraw()

    def canvas_mouseleave(self, event):
        self.hide_handle_tooltip()
        self.cursor_position = None
        self.drag_action = None
        self.drag_target = None
        self.drag_position = None
        self.drag_offset = None
        self.redraw()

    def canvas_mousedown(self, event):
        if event.button not in (MouseButton.LEFT, MouseButton.MIDDLE):
            return
        self.hide_handle_tooltip()
        self.redraw()
        self.cursor_position = (event.x, event.y)

        if self.view_origin is None:
            return

        if event.button == MouseButton.LEFT and self.placement_command is not None:
            command = self.placement_command
            commands = self.placement_commands
            self.move_placement_to_canvas(event.x, event.y)
            self.clear_placement()
            next_values = self.next_placement_values(command, commands)
            if next_values is not None:
                self.append_placement_command(commands, next_values)
            else:
                self.redraw()
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

            shape_handle = self.focused_standalone_handle_at(event.x, event.y)
            if shape_handle is not None:
                world_x, world_y = self.canvas_to_world(event.x, event.y)
                handle_x, handle_y = shape_handle["point"]
                self.drag_action = "shape_handle"
                self.drag_target = shape_handle["kind"]
                self.drag_offset = (handle_x - world_x, handle_y - world_y)
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
                self.drag_position = (world_x, world_y)
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

            command = self.standalone_at(event.x, event.y)
            if command is not None:
                self.focused_command = command
                self.focused_path_commands = None
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
        self.update_handle_tooltip(event.x, event.y)
        self.redraw()

    def hovered_control_handle(self, canvas_x, canvas_y):
        handle = self.focused_handle_at(canvas_x, canvas_y)
        if handle is not None:
            return handle, None

        handle = self.focused_standalone_handle_at(canvas_x, canvas_y)
        if handle is not None:
            return handle["kind"], None

        handle = self.focused_path_handle_at(canvas_x, canvas_y)
        if handle is not None:
            return handle["kind"], handle

        return None

    def control_handle_tooltip(self, kind, handle):
        tooltip = self.HANDLE_TOOLTIPS.get(kind)
        if tooltip is None or handle is None:
            return tooltip

        endpoint_indices = handle.get("endpoint_indices")
        if endpoint_indices is not None:
            start_index, end_index = endpoint_indices
            if start_index is None:
                return f"Start–Endpoint {end_index}: {tooltip}"
            if end_index is None:
                return f"Endpoint {start_index}–Start: {tooltip}"
            return (
                f"Endpoints {start_index}–{end_index}: {tooltip}"
            )

        endpoint_index = handle.get("endpoint_index")
        if endpoint_index is not None:
            return f"Endpoint {endpoint_index}: {tooltip}"
        return tooltip

    def hide_handle_tooltip(self):
        self.handle_tooltip = None

    def update_handle_tooltip(self, canvas_x, canvas_y):
        if self.drag_action is not None or self.placement_command is not None:
            self.hide_handle_tooltip()
            return

        hovered = self.hovered_control_handle(canvas_x, canvas_y)
        if hovered is None:
            self.hide_handle_tooltip()
            return

        kind, handle = hovered
        tooltip = self.control_handle_tooltip(kind, handle)
        if tooltip is None:
            self.hide_handle_tooltip()
            return

        self.handle_tooltip = (tooltip, canvas_x, canvas_y)

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
                self.focused_command[1] = round(world_x + offset_x, 2)
                self.focused_command[2] = round(world_y + offset_y, 2)
        elif self.drag_action == "radius" and self.focused_command is not None:
            geometry = self.circle_geometry(self.focused_command)
            if geometry is not None:
                center_x, _, _ = geometry
                world_x, _ = self.canvas_to_world(event.x, event.y)
                self.focused_command[3] = round(
                    max(
                        0.0,
                        world_x - center_x + self.drag_offset,
                    ),
                    2,
                )
        elif self.drag_action == "path_handle":
            world_x, world_y = self.canvas_to_world(event.x, event.y)
            self.drag_path_handle(world_x, world_y)
        elif self.drag_action == "shape_handle":
            world_x, world_y = self.canvas_to_world(event.x, event.y)
            self.drag_standalone_handle(world_x, world_y)

        self.cursor_position = (event.x, event.y)
        self.move_placement_to_canvas(event.x, event.y)
        self.update_handle_tooltip(event.x, event.y)
        self.redraw()

    def canvas_wheel(self, event):
        if not event.v_delta or self.view_origin is None:
            return

        self.hide_handle_tooltip()
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
            else:
                geometry = self.standalone_geometry(command)
                if geometry is not None and geometry["points"]:
                    x_values = [point[0] for point in geometry["points"]]
                    y_values = [point[1] for point in geometry["points"]]
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

    def fit_view(self):
        if self.canvas_size is None:
            return

        width, height = self.canvas_size
        bounds = self.drawable_bounds()
        if bounds is None:
            self.view_origin = [width / 2, height / 2]
            self.zoom = 1.0
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

    def fit_canvas(self, event):
        self.fit_view()
        self.redraw()

    def move_placement_to_canvas(self, canvas_x, canvas_y):
        if self.placement_command is None or self.view_origin is None:
            return
        world_x, world_y = self.canvas_to_world(canvas_x, canvas_y)
        command = self.placement_command
        command_name = command[0]

        if command_name in self.DIRECT_POSITION_COMMANDS and len(command) >= 3:
            with command:
                command[1] = round(world_x, 2)
                command[2] = round(world_y, 2)
            self.normalize_command(command, self.placement_commands)
            return

        if self.placement_commands is None:
            return
        geometry = self.path_geometry(self.placement_commands, closed=False)
        handles = [
            handle
            for handle in geometry["handles"]
            if handle["command"] is command
        ]

        if command_name == "Turn":
            handle = next(
                (handle for handle in handles if handle["kind"] == "turn"),
                None,
            )
            if handle is None:
                return
            origin_x, origin_y = handle["origin"]
            delta_x = world_x - origin_x
            delta_y = world_y - origin_y
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
                command[1] = round(math.degrees(turn_angle), 2)
                command[2] = round(distance, 2)
            return

        if command_name in ("ArcDegree", "ArcLength"):
            handle = next(
                (handle for handle in handles if handle["kind"] == "arc_center"),
                None,
            )
            if handle is None:
                return
            start_x, start_y = handle["start"]
            delta_x = start_x - world_x
            delta_y = start_y - world_y
            angle = math.atan2(delta_y, delta_x)
            with command:
                command[1] = round(math.degrees(angle), 2)
                command[2] = round(math.hypot(delta_x, delta_y), 2)
            return

        if command_name in ("ToShape", "ToShapeEdge") and len(command) >= 2:
            handle_kind = (
                "to_shape" if command_name == "ToShape" else "to_shape_edge"
            )
            handle = next(
                (handle for handle in handles if handle["kind"] == handle_kind),
                None,
            )
            target_shape = self.shape_named(command[1])
            if handle is None or target_shape is None:
                return
            handle_x, handle_y = handle["point"]
            self.translate_shape(
                target_shape,
                world_x - handle_x,
                world_y - handle_y,
            )

    def begin_placement(
        self,
        command,
        commands=None,
        remove_on_cancel=False,
    ):
        self.hide_handle_tooltip()
        self.placement_command = command
        self.placement_commands = commands
        self.placement_remove_on_cancel = remove_on_cancel
        self.drag_action = None
        self.drag_target = None
        self.drag_position = None
        self.drag_offset = None
        if self.cursor_position is not None:
            self.move_placement_to_canvas(*self.cursor_position)
        self.redraw()

    def clear_placement(self):
        self.placement_command = None
        self.placement_commands = None
        self.placement_remove_on_cancel = False

    @staticmethod
    def next_placement_values(command, commands):
        if (
            commands is None
            or not commands
            or commands[-1] is not command
            or commands[0][0] not in ("Path", "ClosedPath")
        ):
            return None
        if command is commands[0]:
            return ["To", command[1], command[2]]
        return list(command)

    def append_placement_command(self, commands, values):
        command = State(values, deep=True)
        commands.append(command)
        self.focused_command = None
        self.focused_path_commands = commands
        self.begin_placement(
            command,
            commands,
            remove_on_cancel=True,
        )

    def window_keypress(self, event):
        if event.text != "\x1b" or self.placement_command is None:
            return

        command = self.placement_command
        commands = self.placement_commands
        remove_command = self.placement_remove_on_cancel
        self.clear_placement()
        if (
            remove_command
            and commands is not None
            and len(commands) > 1
            and commands[-1] is command
        ):
            commands.pop()
        self.redraw()

    def add_next(self, event, shape):
        commands = shape["commands"]
        geometry = self.path_geometry(commands, closed=False)
        initial_x, initial_y = geometry["points"][-1] if geometry["points"] else (0, 0)
        self.append_placement_command(
            commands,
            ["To", round(initial_x, 2), round(initial_y, 2)],
        )

    def command_changed(self, event, command, shape):
        parameters = self.COMMAND_PARAMETERS.get(command[0])
        if parameters is None:
            return

        with command:
            while len(command) > 1:
                command.pop()
            for _, default in parameters:
                command.append(default)

        commands = shape["commands"]
        if command is commands[0] and command[0] not in ("Path", "ClosedPath"):
            self.focused_command = command
            self.focused_path_commands = None
        else:
            self.focused_command = None
            self.focused_path_commands = commands
        self.begin_placement(command, commands)

    def table_command_changed(self, value, command, shape):
        with command:
            command[0] = str(value)
        self.command_changed(None, command, shape)

    def table_argument_changed(self, value, argument, command, commands):
        argument.value = value
        self.normalize_command(command, commands)

    def add_shape(self, event):
        if self.canvas_size is not None and self.view_origin is not None:
            initial_x, initial_y = self.canvas_to_world(
                self.canvas_size[0] / 2,
                self.canvas_size[1] / 2,
            )
        else:
            initial_x, initial_y = 0, 0
        shape = State(
            {
                "name": "",
                "commands": [
                    ["Point", round(initial_x, 2), round(initial_y, 2)]
                ],
            },
            deep=True,
        )
        self.state.shape_expanded.append(False)
        self.state.shapes.append(shape)
        command = shape["commands"][0]
        self.focused_command = command
        self.focused_path_commands = None
        self.begin_placement(command, shape["commands"])

    def toggle_shape(self, event, shape_idx):
        self.state.shape_expanded[shape_idx] = not self.state.shape_expanded[shape_idx]

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

    @staticmethod
    def svg_number(value):
        value = round(float(value), 2)
        if value == 0:
            value = 0
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def svg_path(self, points, closed, color):
        if not points:
            return None
        if len(points) == 1:
            point_x, point_y = points[0]
            return (
                f'<circle cx="{self.svg_number(point_x)}" '
                f'cy="{self.svg_number(point_y)}" '
                f'r="{self.svg_number(self.SVG_POINT_RADIUS)}" '
                f'fill="{color}" />'
            )

        path_points = list(points)
        if closed and path_points[-1] == path_points[0]:
            path_points.pop()
        coordinates = " ".join(
            (
                f"M {self.svg_number(point_x)} {self.svg_number(point_y)}"
                if index == 0
                else f"L {self.svg_number(point_x)} {self.svg_number(point_y)}"
            )
            for index, (point_x, point_y) in enumerate(path_points)
        )
        close_command = " Z" if closed else ""
        return (
            f'<path d="{coordinates}{close_command}" fill="none" '
            f'stroke="{color}" stroke-width="1" '
            f'vector-effect="non-scaling-stroke" />'
        )

    def svg_document(self):
        bounds = self.drawable_bounds()
        if bounds is None:
            min_x, min_y, max_x, max_y = 0, 0, 100, 100
            padding = 0
        else:
            min_x, min_y, max_x, max_y = bounds
            padding = self.SVG_PADDING

        view_x = min_x - padding
        view_y = -(max_y + padding)
        width = max(1, max_x - min_x + 2 * padding)
        height = max(1, max_y - min_y + 2 * padding)
        elements = []

        for shape_index, shape in enumerate(self.state.shapes):
            commands = shape["commands"]
            if not commands:
                continue
            command = commands[0]
            command_name = command[0]
            element = None

            if command_name == "Circle":
                geometry = self.circle_geometry(command)
                if geometry is not None:
                    center_x, center_y, radius = geometry
                    element = (
                        f'<circle cx="{self.svg_number(center_x)}" '
                        f'cy="{self.svg_number(center_y)}" '
                        f'r="{self.svg_number(radius)}" fill="none" '
                        f'stroke="#2563EB" stroke-width="1" '
                        f'vector-effect="non-scaling-stroke" />'
                    )
            elif command_name in ("Path", "ClosedPath"):
                geometry = self.path_geometry(
                    commands,
                    closed=command_name == "ClosedPath",
                )
                element = self.svg_path(
                    geometry["points"],
                    command_name == "ClosedPath",
                    "#0F766E",
                )
            else:
                geometry = self.standalone_geometry(command)
                if geometry is not None:
                    element = self.svg_path(
                        geometry["points"],
                        geometry["closed"],
                        "#2563EB",
                    )

            if element is None:
                continue
            name = str(shape.get("name", ""))
            name_attribute = f" data-name={quoteattr(name)}" if name else ""
            elements.append(
                f'    <g id="shape-{shape_index}"{name_attribute}>\n'
                f"        {element}\n"
                "    </g>"
            )

        body = "\n".join(elements)
        if body:
            body += "\n"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.svg_number(width)}" '
            f'height="{self.svg_number(height)}" '
            f'viewBox="{self.svg_number(view_x)} {self.svg_number(view_y)} '
            f'{self.svg_number(width)} {self.svg_number(height)}">\n'
            '  <g transform="scale(1,-1)">\n'
            f"{body}"
            "  </g>\n"
            "</svg>\n"
        )

    def export_svg(self, event):
        output_path = SaveFile(
            default=str(self.input_path.with_suffix(".svg")),
            title="Export ShapeCmd SVG",
            types="SVG Files (*.svg)|All Files (*)",
        )
        if output_path is None:
            return
        Path(output_path).write_text(self.svg_document(), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} INPUT.json")

    app = ShapeCmd(sys.argv[1])
    app.run()
