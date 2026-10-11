# Shape或Path起點
- Point: x, y
- Circle:  center_x, center_y, radius
- Arc: center_x, center_y, radius, start_angle, span_deg, direction (CW/CCW)
- Rect: x, y, x_offset, y_offset
- CenterRect: center_x, center_y, width, height
- RegularPolygon: center_x, center_y, radius, sides, rotate_deg

- Path: x, y
- ClosePath: x, y

# Path Next
- ArcDeg: angle, radius, span_deg, direction (CW/CCW)
- ArcRad: angle, radius, span_radian, direction (CW/CCW)
- Turn: angle, distance
- To: x, y
- BezierTo: x, y (終點；控制點依前一段方向自動計算)
- ToShape: name（連到 target shape 的 x/y）
- ToShapeEdge: name（連到 target shape 邊界上的最近點）
