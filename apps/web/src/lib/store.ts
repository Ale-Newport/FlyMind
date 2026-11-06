import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Neuron, StimulusSpec, InterventionSpec } from "./types";

// Colour theme state lives in ./theme (own storage key); re-exported here for convenience.
export { useTheme, useThemeStore } from "./theme";
export type { ThemePref, ResolvedTheme } from "./theme";

export type ColorField = "super_class" | "primary_neuropil" | "nt_type" | "cell_type" | "side" | "activity";

interface PendingAction {
  kind: "stimulate" | "silence" | "probe";
  datasetId: string;
  rootIds: string[];
  label: string;
}

interface AppState {
  datasetId: string;
  setDatasetId: (id: string) => void;
  // explorer
  selected: Neuron | null;
  setSelected: (n: Neuron | null) => void;
  highlight: { idx: number[]; label: string } | null;
  setHighlight: (h: { idx: number[]; label: string } | null) => void;
  colorField: ColorField;
  setColorField: (f: ColorField) => void;
  pointSize: number;
  setPointSize: (v: number) => void;
  opacity: number;
  setOpacity: (v: number) => void;
  // simulation linkage
  simSessionId: string | null;
  setSimSessionId: (id: string | null) => void;
  pending: PendingAction | null;
  setPending: (p: PendingAction | null) => void;
  // drafts used when creating sessions from other modules
  draftStimuli: StimulusSpec[];
  draftInterventions: InterventionSpec[];
  setDrafts: (s: StimulusSpec[], i: InterventionSpec[]) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      datasetId: "synthetic_demo_v1",
      setDatasetId: (datasetId) => set({ datasetId, selected: null, highlight: null }),
      selected: null,
      setSelected: (selected) => set({ selected }),
      highlight: null,
      setHighlight: (highlight) => set({ highlight }),
      colorField: "super_class",
      setColorField: (colorField) => set({ colorField }),
      pointSize: 2.2,
      setPointSize: (pointSize) => set({ pointSize }),
      opacity: 0.55,
      setOpacity: (opacity) => set({ opacity }),
      simSessionId: null,
      setSimSessionId: (simSessionId) => set({ simSessionId }),
      pending: null,
      setPending: (pending) => set({ pending }),
      draftStimuli: [],
      draftInterventions: [],
      setDrafts: (draftStimuli, draftInterventions) => set({ draftStimuli, draftInterventions }),
    }),
    {
      name: "flymind-prefs",
      // only persist user preferences, never transient scientific state
      partialize: (s) => ({ datasetId: s.datasetId, colorField: s.colorField, pointSize: s.pointSize, opacity: s.opacity }),
    },
  ),
);
