"use client";

import { Agentation } from "agentation";

/** Renders the visual-feedback toolbar only while developing locally. */
export default function AgentationDev() {
  if (process.env.NODE_ENV !== "development") {
    return null;
  }

  return <Agentation />;
}
