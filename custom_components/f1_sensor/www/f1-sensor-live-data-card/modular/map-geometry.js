const MAX_DEVIATION = .35;
const FLATNESS = .025;
const samePoint = (a, b) => a[0] === b[0] && a[1] === b[1];
const midpoint = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
const reflect = (anchor, neighbor) => [2 * anchor[0] - neighbor[0], 2 * anchor[1] - neighbor[1]];
const coordinate = value => Number(value.toFixed(6));

// Keep the display curve inside the normal track stroke. Forward, short
// handles also prevent a sparse or sharply turning source from making loops.
function boundedControl(anchor, end, candidate) {
  const dx = end[0] - anchor[0], dy = end[1] - anchor[1], length = Math.hypot(dx, dy);
  const vx = candidate[0] - anchor[0], vy = candidate[1] - anchor[1], handle = Math.hypot(vx, vy);
  if (!length || !handle || vx * dx + vy * dy <= 0) return anchor;
  const sideways = Math.abs(vx * dy - vy * dx) / length;
  const factor = Math.min(1, length * .45 / handle, sideways ? MAX_DEVIATION / sideways : 1);
  return [coordinate(anchor[0] + vx * factor), coordinate(anchor[1] + vy * factor)];
}

function controls(p0, p1, p2, p3) {
  const d1 = Math.sqrt(Math.hypot(p1[0] - p0[0], p1[1] - p0[1]));
  const d2 = Math.sqrt(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]));
  const d3 = Math.sqrt(Math.hypot(p3[0] - p2[0], p3[1] - p2[1]));
  const first = d1 && d2 ? [0, 1].map(axis => p1[axis] + d2 / 3 * (
    (p1[axis] - p0[axis]) / d1 - (p2[axis] - p0[axis]) / (d1 + d2) + (p2[axis] - p1[axis]) / d2)) : p1;
  const second = d2 && d3 ? [0, 1].map(axis => p2[axis] - d2 / 3 * (
    (p2[axis] - p1[axis]) / d2 - (p3[axis] - p1[axis]) / (d2 + d3) + (p3[axis] - p2[axis]) / d3)) : p2;
  return [boundedControl(p1, p2, first), boundedControl(p2, p1, second)];
}

function distanceToChord(point, start, end) {
  const dx = end[0] - start[0], dy = end[1] - start[1], length = Math.hypot(dx, dy);
  return length ? Math.abs((point[0] - start[0]) * dy - (point[1] - start[1]) * dx) / length : Math.hypot(point[0] - start[0], point[1] - start[1]);
}

// Subdivide the same Bézier that is drawn so collision checks also see its
// curved portions. No segment is ever inserted across a source-data gap.
function flatten(start, first, second, end, segments, depth = 0) {
  if (depth >= 12 || Math.max(distanceToChord(first, start, end), distanceToChord(second, start, end)) <= FLATNESS) {
    segments.push([start, end]);
    return;
  }
  const a = midpoint(start, first), b = midpoint(first, second), c = midpoint(second, end);
  const d = midpoint(a, b), e = midpoint(b, c), center = midpoint(d, e);
  flatten(start, a, d, center, segments, depth + 1);
  flatten(center, e, c, end, segments, depth + 1);
}

export function displayTrack(points, smooth = false) {
  const runs = []; let run = [];
  for (const point of points ?? []) {
    if (!Array.isArray(point) || point.length < 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
      if (run.length) runs.push(run);
      run = [];
    } else if (!run.length || !samePoint(run.at(-1), point)) run.push(point);
  }
  if (run.length) runs.push(run);
  const commands = [], segments = [];
  for (const actual of runs) {
    commands.push(`M${actual[0][0]},${actual[0][1]}`);
    const closed = actual.length > 3 && samePoint(actual[0], actual.at(-1));
    const count = closed ? actual.length - 1 : actual.length;
    const at = index => closed ? actual[(index % count + count) % count]
      : index < 0 ? reflect(actual[0], actual[1])
      : index >= count ? reflect(actual.at(-1), actual.at(-2)) : actual[index];
    for (let index = 1; index < actual.length; index++) {
      const start = actual[index - 1], end = actual[index];
      if (!smooth || actual.length < 3) {
        commands.push(`L${end[0]},${end[1]}`);
        segments.push([start, end]);
      } else {
        const [first, second] = controls(at(index - 2), start, end, at(index + 1));
        commands.push(`C${first[0]},${first[1]} ${second[0]},${second[1]} ${end[0]},${end[1]}`);
        flatten(start, first, second, end, segments);
      }
    }
  }
  return { path: commands.join(' '), segments };
}
