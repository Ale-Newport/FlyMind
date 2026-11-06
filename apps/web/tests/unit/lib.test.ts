import { describe, expect, it } from "vitest";
import { categoryColor, hashColor, hexToRgb, rateColor } from "../../src/lib/colors";
import { decodeB64 } from "../../src/lib/api";
import { toDisplay } from "../../src/three/BrainScene";

describe("colours", () => {
  it("are deterministic and consistent across views", () => {
    expect(hashColor("AL_L")).toBe(hashColor("AL_L"));
    expect(categoryColor("nt_type", "GABA")).toBe("#f43f5e");
    expect(categoryColor("super_class", "descending")).toBe("#f472b6");
    expect(hexToRgb("#ff0000")).toEqual([1, 0, 0]);
  });
  it("rate ramp is clamped and monotonic in brightness", () => {
    const lum = (c: number[]) => c[0] + c[1] + c[2];
    expect(lum(rateColor(-1))).toBeCloseTo(lum(rateColor(0)));
    expect(lum(rateColor(1))).toBeGreaterThan(lum(rateColor(0.5)));
    expect(lum(rateColor(0.5))).toBeGreaterThan(lum(rateColor(0)));
  });
});

describe("binary decoding", () => {
  it("decodes base64 float32 buffers exactly", () => {
    const src = new Float32Array([1.5, -2.25, 3e5]);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(src.buffer)));
    expect(Array.from(new Float32Array(decodeB64(b64)))).toEqual([1.5, -2.25, 3e5]);
  });
});

describe("anatomical display transform", () => {
  it("maps FlyWire (+x right, +y ventral, +z posterior) to display (right, dorsal up, anterior +Z)", () => {
    const c: [number, number, number] = [10, 20, 30];
    expect(toDisplay(11, 20, 30, c)).toEqual([1, -0, -0]);
    expect(toDisplay(10, 25, 30, c)[1]).toBe(-5); // more ventral -> lower on screen
    expect(toDisplay(10, 20, 35, c)[2]).toBe(-5); // more posterior -> away from viewer
  });
});

describe("root IDs", () => {
  it("are kept as strings because they exceed Number.MAX_SAFE_INTEGER", () => {
    const id = "720575940629970489";
    expect(Number(id) > Number.MAX_SAFE_INTEGER).toBe(true);
    expect(String(Number(id))).not.toBe(id); // a JS number would corrupt it
    expect(BigInt(id).toString()).toBe(id);
  });
});
