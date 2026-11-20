"use client";

import { useState } from "react";
import ResultPanel from "./components/ResultPanel";

type FormState = {
  dwelling_type: string;
  extension_position: string;
  storeys: string;
  rear_depth_m: string;
  height_m: string;
  eaves_height_m: string;
  side_width_ratio: string;
  curtilage_cover_ratio: string;
  exceeds_highest_roof: string;
  exceeds_existing_eaves: string;
  beyond_principal_elevation: string;
  cladding: string;
  includes_verandah_balcony_platform: string;
  article_2_3_land: string;
  article_4: string;
  listed: string;
};

const EMPTY: FormState = {
  dwelling_type: "",
  extension_position: "",
  storeys: "",
  rear_depth_m: "",
  height_m: "",
  eaves_height_m: "",
  side_width_ratio: "",
  curtilage_cover_ratio: "",
  exceeds_highest_roof: "",
  exceeds_existing_eaves: "",
  beyond_principal_elevation: "",
  cladding: "",
  includes_verandah_balcony_platform: "",
  article_2_3_land: "",
  article_4: "",
  listed: "",
};

function parseOptionalFloat(v: string): number | null {
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

function parseOptionalInt(v: string): number | null {
  const n = parseInt(v, 10);
  return isNaN(n) ? null : n;
}

function parseOptionalBool(v: string): boolean | null {
  if (v === "true") return true;
  if (v === "false") return false;
  return null;
}

export default function Home() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(field: keyof FormState, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const body = {
      dwelling_type: form.dwelling_type || null,
      extension_position: form.extension_position || null,
      storeys: parseOptionalInt(form.storeys),
      rear_depth_m: parseOptionalFloat(form.rear_depth_m),
      height_m: parseOptionalFloat(form.height_m),
      eaves_height_m: parseOptionalFloat(form.eaves_height_m),
      side_width_ratio: parseOptionalFloat(form.side_width_ratio),
      curtilage_cover_ratio: parseOptionalFloat(form.curtilage_cover_ratio),
      exceeds_highest_roof: parseOptionalBool(form.exceeds_highest_roof),
      exceeds_existing_eaves: parseOptionalBool(form.exceeds_existing_eaves),
      beyond_principal_elevation: parseOptionalBool(form.beyond_principal_elevation),
      cladding: parseOptionalBool(form.cladding),
      includes_verandah_balcony_platform: parseOptionalBool(form.includes_verandah_balcony_platform),
      article_2_3_land: parseOptionalBool(form.article_2_3_land),
      article_4: parseOptionalBool(form.article_4),
      listed: parseOptionalBool(form.listed),
    };

    try {
      const res = await fetch("http://localhost:8000/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">
            Householder PD Pre-check
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            GPDO 2015 Schedule 2 Part 1 Class A — permitted development checker.
            Not a substitute for professional advice or a formal LDC application.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Section 1: Property */}
          <Section title="Property">
            <Field label="Dwelling type">
              <Select
                value={form.dwelling_type}
                onChange={(v) => set("dwelling_type", v)}
                options={[
                  ["", "Select…"],
                  ["detached", "Detached"],
                  ["semi", "Semi-detached"],
                  ["terraced", "Terraced"],
                  ["flat", "Flat"],
                ]}
              />
            </Field>
            <Field label="Extension position">
              <Select
                value={form.extension_position}
                onChange={(v) => set("extension_position", v)}
                options={[
                  ["", "Select…"],
                  ["rear", "Rear"],
                  ["side", "Side"],
                  ["front", "Front"],
                ]}
              />
            </Field>
            <Field label="Number of storeys">
              <Select
                value={form.storeys}
                onChange={(v) => set("storeys", v)}
                options={[
                  ["", "Select…"],
                  ["1", "Single-storey"],
                  ["2", "Two-storey"],
                ]}
              />
            </Field>
          </Section>

          {/* Section 2: Dimensions */}
          <Section title="Dimensions">
            <Field label="Rear extension depth (m)" hint="Measured from rear wall of original house">
              <NumberInput value={form.rear_depth_m} onChange={(v) => set("rear_depth_m", v)} />
            </Field>
            <Field label="Maximum height (m)" hint="Ridge height of the extension">
              <NumberInput value={form.height_m} onChange={(v) => set("height_m", v)} />
            </Field>
            <Field label="Eaves height (m)">
              <NumberInput value={form.eaves_height_m} onChange={(v) => set("eaves_height_m", v)} />
            </Field>
            <Field label="Side width ratio" hint="Extension width ÷ original house width (e.g. 0.4 = 40%)">
              <NumberInput value={form.side_width_ratio} onChange={(v) => set("side_width_ratio", v)} step="0.01" />
            </Field>
            <Field label="Curtilage cover ratio" hint="Total outbuildings + extensions ÷ original curtilage (e.g. 0.3 = 30%)">
              <NumberInput value={form.curtilage_cover_ratio} onChange={(v) => set("curtilage_cover_ratio", v)} step="0.01" />
            </Field>
          </Section>

          {/* Section 3: Yes/No questions */}
          <Section title="Additional checks">
            <Field label="Does the extension exceed the highest part of the existing roof?">
              <BoolSelect value={form.exceeds_highest_roof} onChange={(v) => set("exceeds_highest_roof", v)} />
            </Field>
            <Field label="Does the extension exceed the eaves of the existing roof?">
              <BoolSelect value={form.exceeds_existing_eaves} onChange={(v) => set("exceeds_existing_eaves", v)} />
            </Field>
            <Field label="Does the extension project beyond the principal elevation?">
              <BoolSelect value={form.beyond_principal_elevation} onChange={(v) => set("beyond_principal_elevation", v)} />
            </Field>
            <Field label="Does it include a veranda, balcony or raised platform?">
              <BoolSelect value={form.includes_verandah_balcony_platform} onChange={(v) => set("includes_verandah_balcony_platform", v)} />
            </Field>
            <Field label="Does it use cladding on the exterior?">
              <BoolSelect value={form.cladding} onChange={(v) => set("cladding", v)} />
            </Field>
          </Section>

          {/* Section 4: Constraints */}
          <Section title="Planning constraints" hint="If unsure, leave as Unknown — constraint lookup coming soon">
            <Field label="Article 2(3) land?" hint="Conservation area, National Park, AONB, World Heritage Site">
              <BoolSelect value={form.article_2_3_land} onChange={(v) => set("article_2_3_land", v)} />
            </Field>
            <Field label="Article 4 direction applies?">
              <BoolSelect value={form.article_4} onChange={(v) => set("article_4", v)} />
            </Field>
            <Field label="Listed building?">
              <BoolSelect value={form.listed} onChange={(v) => set("listed", v)} />
            </Field>
          </Section>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-semibold rounded-lg transition-colors"
          >
            {loading ? "Checking…" : "Check permitted development"}
          </button>
        </form>

        {error && (
          <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}. Is the API running on port 8000?
          </div>
        )}

        {result && <ResultPanel result={result} />}
      </div>
    </main>
  );
}

/* ── Small shared components ── */

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h2 className="text-base font-semibold text-gray-800 mb-1">{title}</h2>
      {hint && <p className="text-xs text-gray-400 mb-3">{hint}</p>}
      <div className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-700">{label}</p>
        {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
      </div>
      <div className="shrink-0 w-44">{children}</div>
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
    >
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  );
}

function BoolSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Select
      value={value}
      onChange={onChange}
      options={[
        ["", "Unknown"],
        ["true", "Yes"],
        ["false", "No"],
      ]}
    />
  );
}

function NumberInput({
  value,
  onChange,
  step = "0.1",
}: {
  value: string;
  onChange: (v: string) => void;
  step?: string;
}) {
  return (
    <input
      type="number"
      min="0"
      step={step}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="—"
      className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
    />
  );
}
