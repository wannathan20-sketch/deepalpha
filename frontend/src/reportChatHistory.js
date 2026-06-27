export function getReportChatItemKey(item) {
  return item?.message_id || item?.id || `${item?.created_at || "chat"}-${item?.question || ""}`;
}

export function deleteReportChatMessage(items, messageKey) {
  if (!messageKey) return items;
  return items.filter((item) => getReportChatItemKey(item) !== messageKey);
}
