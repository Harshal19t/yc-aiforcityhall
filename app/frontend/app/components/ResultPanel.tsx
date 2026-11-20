"use client";

import { useState } from "react";

type Finding = {
  rule_id: string;
  outcome: string;
  description: string;
  citation: string;
  verify: boolean;
};

type ConstraintInfo = {
  article_2_3_land: boolean | null;
  article_4: boolean | null;
  listed: boolean | null;
  missing_datasets: string[];
  source: string;
};

type CheckResponse = {
  status: string;
  findings: Finding[];
  other_consents: Finding[];
  unknown_fields: string[];
  constraints: ConstraintInfo;
};

const STATUS_CONFIG: Record<
  string,
  { label: string; bg: string; text: string; border: string; icon: string }
> = {
  likely_permitted: {
    label: "Likely permitted development",
    bg: "bg-green-50",
    text: "text-green-800",
    border: "border-green-300",
    icon: "✓",
  },
  prior_approval_possible: {
    label: "May need prior approval",
    bg: "bg-amber-50",
    text: "text-amber-800",
    border: "border-amber-300",
    icon: "⚠",
  },
  needs_review: {
    label: "Needs professional review",
    bg: "bg-orange-50",
    text: "text-orange-800",
    border: "border-orange-300",
    icon: "⚠",
  },
  needs_permission: {
    label: "Full planning permission required",
    bg: "bg-red-50",
    text: "text-red-800",
    border: "border-red-300",
    icon: "✗",
  },
};

const OUTCOME_DOT: Record<string, string> = {
  pass: "bg-green-500",
  fail: "bg-red-500",
  unknown: "bg-gray-300",
  info: "bg-blue-400",
};

export default function ResultPanel({ result }: { result: unknown }) {
  const res = result as CheckResponse;
  const cfg = STATUS_CONFIG[res.status] ?? {
    label: res.status,
    bg: "bg-gray-50",
    text: "text-gray-800",
    border: "border-gray-300",
    icon: "?",
  };

  const fails = res.findings.filter((f) => f.outcome === "fail");
  const passes = res.findings.filter((f) => f.outcome === "pass");
  const unknowns = res.findings.filter((f) => f.outcome === "unknown");

  return (
    <div className="mt-8 space-y-4">
      {/* Verdict banner */}
      <div
        className={`flex items-start gap-3 p-4 rounded-xl border-2 ${cfg.bg} ${cfg.border}`}
      >
        <span className={`text-2xl font-bold ${cfg.text} leading-none mt-0.5`}>
          {cfg.icon}
        </span>
        <div>
          <p className={`font-semibold text-lg ${cfg.text}`}>{cfg.label}</p>
          <p className="text-sm text-gray-500 mt-0.5">
            This is a preliminary check only — not legal advice.
          </p>
        </div>
      </div>

      {/* Findings that caused a fail */}
      {fails.length > 0 && (
        <FindingGroup
          title={`${fails.length} rule${fails.length > 1 ? "s" : ""} not met`}
          findings={fails}
          dotClass="bg-red-500"
          defaultOpen
        />
      )}

      {/* Unknowns (couldn't assess) */}
      {unknowns.length > 0 && (
        <FindingGroup
          title={`${unknowns.length} rule${unknowns.length > 1 ? "s" : ""} couldn't be assessed`}
          findings={unknowns}
          dotClass="bg-gray-400"
          defaultOpen={fails.length === 0}
        />
      )}

      {/* Passes */}
      {passes.length > 0 && (
        <FindingGroup
          title={`${passes.length} rule${passes.length > 1 ? "s" : ""} passed`}
          findings={passes}
          dotClass="bg-green-500"
          defaultOpen={false}
        />
      )}

      {/* Other consents */}
      {res.other_consents.length > 0 && (
        <FindingGroup
          title="Other consents may also be required"
          findings={res.other_consents}
          dotClass="bg-blue-400"
          defaultOpen
        />
      )}

      {/* Unknown fields */}
      {res.unknown_fields.length > 0 && (
        <div className="text-xs text-gray-400 p-3 bg-gray-50 rounded-lg border border-gray-100">
          <span className="font-medium text-gray-500">Missing info: </span>
          {res.unknown_fields.join(", ")}
        </div>
      )}

      {/* Constraints */}
      <ConstraintBadges constraints={res.constraints} />

      {/* Disclaimer */}
      <p className="text-xs text-gray-400 leading-relaxed pt-2">
        Rules checked against GPDO 2015 Schedule 2 Part 1 Class A. This tool
        does not check all conditions and cannot substitute for a formal Lawful
        Development Certificate application or professional advice.
      </p>
    </div>
  );
}

function FindingGroup({
  title,
  findings,
  dotClass,
  defaultOpen,
}: {
  title: string;
  findings: Finding[];
  dotClass: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <span className={`w-2 h-2 rounded-full ${dotClass}`} />
          {title}
        </span>
        <span className="text-gray-400 text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="divide-y divide-gray-100">
          {findings.map((f) => (
            <li key={f.rule_id} className="px-4 py-3 bg-white">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800">{f.description}</p>
                  <p className="text-xs text-gray-400 mt-1">{f.citation}</p>
                  {f.verify && (
                    <span className="inline-block mt-1.5 text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 rounded px-1.5 py-0.5">
                      verify on site
                    </span>
                  )}
                </div>
                <span className="shrink-0 text-xs font-mono text-gray-300">
                  {f.rule_id}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConstraintBadges({ constraints }: { constraints: ConstraintInfo }) {
  const items = [
    { label: "Article 2(3)", value: constraints.article_2_3_land },
    { label: "Article 4", value: constraints.article_4 },
    { label: "Listed", value: constraints.listed },
  ];

  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {items.map(({ label, value }) => (
        <span
          key={label}
          className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border ${
            value === true
              ? "bg-red-50 text-red-700 border-red-200"
              : value === false
              ? "bg-gray-50 text-gray-500 border-gray-200"
              : "bg-gray-50 text-gray-400 border-gray-100 italic"
          }`}
        >
          {label}:{" "}
          {value === true ? "yes" : value === false ? "no" : "unknown"}
        </span>
      ))}
      {constraints.missing_datasets.length > 0 && (
        <span className="text-xs text-gray-400 self-center">
          (datasets missing: {constraints.missing_datasets.join(", ")})
        </span>
      )}
    </div>
  );
}
