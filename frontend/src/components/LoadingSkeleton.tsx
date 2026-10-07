"use client";

import React from "react";

export default function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Timeline skeleton */}
      <div className="h-16 bg-slate-900/60 border border-slate-800 rounded-2xl w-full" />

      {/* KPI Cards skeleton */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-32 bg-slate-900/60 border border-slate-800 rounded-2xl"
          />
        ))}
      </div>

      {/* Macro chart skeleton */}
      <div className="h-96 bg-slate-900/60 border border-slate-800 rounded-2xl w-full" />

      {/* Legislative panel skeleton */}
      <div className="h-72 bg-slate-900/60 border border-slate-800 rounded-2xl w-full" />
    </div>
  );
}
