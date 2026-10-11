# Shape或Path起點
- Point: x, y
- Circle:  center_x, center_y, radius
- Arc: center_x, center_y, start_angle, span_deg
- Rect: x, y, x_offset, y_offset
- CenterRect: center_x, center_y, width, height
- RegularPolygon: center_x, center_y, radius, sides, rotate_deg

- Path: x, y
- ClosePath: x, y

# Path Next
- ArcDeg: angle, span_deg
- ArcRad: angle, span_radian
- Turn: angle, distance
- To: x, y
- BezierTo: x, y
- ToShape: name
