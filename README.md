# ShapeCmd

ShapeCmd is an interactive 2D shape-command editor built with PUI and PySide6.
The canvas on the left provides previews and drag editing, while the panel on
the right edits command parameters. Shape data is loaded from and saved to JSON.

## Installation and Usage

```sh
python -m venv env
source env/bin/activate
pip install -r requirements.txt
python shapecmd.py input.json
```

The application loads the JSON file specified by `argv[1]`. Clicking `Save`
opens a PUI `SaveFile` dialog with `argv[1]` as the default output path.

## JSON Format

Each shape has a name and a list of commands. A command uses a compact array
format: the first element is the command name, followed by its arguments in
order.

```json
{
    "shapes": [
        {
            "name": "target",
            "commands": [
                ["Circle", 100, 100, 50]
            ]
        },
        {
            "name": "route",
            "commands": [
                ["Path", 0, 0],
                ["To", 50, 80],
                ["ToShapeEdge", "target"]
            ]
        }
    ]
}
```

The positive X axis points right and the positive Y axis points up. Angles use
degrees. Floating-point values are rounded to two decimal places after loading,
field editing, or dragging. Expansion state in the right panel is UI-only and
is not written to JSON.

## Initial Commands

The first command of each shape must be one of the following:

| Command | Arguments | Description |
| --- | --- | --- |
| `Point` | `x, y` | A single point. |
| `Circle` | `centerX, centerY, radius` | A circle. |
| `Arc` | `centerX, centerY, radius, startAngle, spanDeg, direction` | A standalone arc. `direction` is `CW` or `CCW`. |
| `Rect` | `x, y, xOffset, yOffset, rotateDeg` | A rectangle defined by an origin and local offsets, rotated around its origin. |
| `CenterRect` | `centerX, centerY, width, height, rotateDeg` | A rectangle defined by its center and size, rotated around its center. |
| `RegularPolygon` | `centerX, centerY, radius, sides, rotateDeg` | A regular polygon. `sides` is clamped to `3`–`1000`, and the corrected value is written back to the model. |
| `Path` | `x, y` | The starting point of an open path. |
| `ClosedPath` | `x, y` | A closed path that automatically returns to its starting point. |

## Path Commands

Use `Add Next` to append any of the following commands to a `Path` or
`ClosedPath`:

| Command | Arguments | Description |
| --- | --- | --- |
| `To` | `x, y` | Draws to an absolute coordinate. |
| `Turn` | `angle, distance` | Turns relative to the current heading, then advances by the specified distance. |
| `BezierTo` | `x, y` | Draws to the endpoint using cubic Bézier control points calculated from the previous heading. |
| `ArcDegree` | `angle, radius, spanDeg, direction` | Draws an arc from the current point. The angle and span use degrees. |
| `ArcLength` | `angle, radius, arcLength, direction` | Draws an arc from the current point with its extent specified as a linear arc length. |
| `ArcTo` | `x, y, radius, direction` | Draws the minor arc to a fixed endpoint. The radius is clamped to at least half the distance from the start to the endpoint, and the corrected value is written back to the model. |
| `ToShape` | `name` | Draws to the target shape's reference x/y coordinate. |
| `ToShapeEdge` | `name` | Draws to the nearest point on the target shape's boundary. |

For `ArcDegree` and `ArcLength`, `angle` is the angle from the inferred center to
the arc's starting point. The center is calculated from the current path
position, angle, and radius. `direction` is `CW` or `CCW`. For `ArcLength`, the
angular span in radians is calculated as `arcLength / radius`. `ArcTo` derives
its center from the start, fixed endpoint, radius, and direction; the minimum
radius produces a semicircle.

Radius parameters and `arcLength` default to `50`. Degree-based arc spans
default to `30`.

The reference x/y coordinate used by `ToShape` depends on the target shape:

- `Point`: point coordinates.
- `Circle`, `Arc`, `CenterRect`, and `RegularPolygon`: center coordinates.
- `Rect`: origin coordinates.
- `Path` and `ClosedPath`: starting coordinates.

Referenced shapes should have unique, non-empty names. If multiple shapes have
the same name, the first match is used. `ToShapeEdge` calculates an exact nearest
point for circles and approximates other shapes using their rendered line
segments.

## Controls

- Mouse wheel: zoom around the cursor.
- Drag an empty area with the left mouse button, or drag with the middle mouse
  button: pan the canvas.
- Click a shape: focus it and enter edit mode.
- The initial view automatically fits all shapes inside the canvas with 100 px
  of padding.
- `Fit`: restore the same fitted view at any time.
- `Display Arrow`: show or hide direction arrows on the focused path.
- `Show`/`Hide` next to a shape name: expand or collapse its commands. Shapes
  are collapsed by default.
- Each expanded shape has its own command table. Double-click a cell to edit
  it; for paths, the leftmost read-only column shows the zero-based command
  index as its endpoint index. The path-start index `0` is hidden, so visible
  endpoint indexes begin at `1`. Command and Direction cells use drop-down
  editors.
- Changing a command type re-enters placement mode. Direct-position commands
  follow the pointer, `Turn` places its endpoint, and path arcs place their
  center.
- Path placement is continuous. Placing a `Path` or `ClosedPath` start point
  creates a pending `To`; placing a next command creates another command of the
  same type. Press Escape to stop placement and remove the pending command.
- `Add Next`: append a pending `To` command and enter continuous placement.
- `Add Shape`: add a shape initialized with a `Point`, then move it with the
  pointer until the next left click places it.
- `Save`: choose an output path and save the JSON data.
- `Export SVG`: export all shapes without canvas axes, focus handles, or
  direction arrows. The SVG view box is fitted to the exported geometry.

## Focus Handles

- `Point`: position.
- `Circle`: center and right-side radius handle.
- `Arc`: center, start, end, and an `R/2` radius handle on the start side.
- `Rect`: origin, opposite corner, and rotation handle.
- `CenterRect`: center, upper-right corner, and rotation handle.
- `RegularPolygon`: center and first vertex. The vertex controls both the radius
  and `rotateDeg`.
- `Path` and `ClosedPath`: starting point, editable command endpoints, and a
  midpoint handle on every segment. Dragging a midpoint translates both
  endpoints of that segment. Handle tooltips use the same zero-based endpoint
  indexes shown in the command table.
- `ArcDegree` and `ArcLength`: center, endpoint, and the original `R/2` radius
  handle on the start side.
- `ArcTo`: endpoint and a radius handle on a short, fixed-screen-length stem
  extending from the arc midpoint toward the center. Dragging it preserves
  both endpoints and direction without displaying the full radius.
- `ToShape` and `ToShapeEdge`: dragging the derived endpoint moves the referenced
  target shape.
