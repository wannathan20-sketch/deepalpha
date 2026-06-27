import assert from "node:assert/strict";
import { test } from "node:test";

import { deleteReportChatMessage, getReportChatItemKey } from "./reportChatHistory.js";

test("uses backend message_id as the stable report chat item key", () => {
  assert.equal(
    getReportChatItemKey({ message_id: "backend-message", created_at: "2026-06-27", question: "Why?" }),
    "backend-message",
  );
});

test("deletes only the selected persisted report chat message", () => {
  const items = [
    { message_id: "first", question: "Q1" },
    { message_id: "second", question: "Q2" },
  ];

  assert.deepEqual(deleteReportChatMessage(items, "first"), [
    { message_id: "second", question: "Q2" },
  ]);
});
