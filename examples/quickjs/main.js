import * as hg from 'example';

const p = new hg.Vec3(1, 2, 3);
const next = p.add(new hg.Vec3(0, 1, 0).mul(0.016));
const [visible, x, y] = hg.project(next);
if (!visible || x !== 1 || y <= 2) throw new Error('projection failed');
if (hg.timestamp() !== 9007199254740993n) throw new Error('lost timestamp precision');
if (!p.equals(new hg.Vec3(1, 2, 3))) throw new Error('value comparison failed');
