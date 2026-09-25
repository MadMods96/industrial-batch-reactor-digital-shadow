"use client";

import { Fragment, type ReactNode } from "react";

/** Lightweight Markdown → React. No HTML injection. */
export function MarkdownText({ text }: { text: string }) {
  const blocks = splitBlocks(text.trim());
  return (
    <div className="md-body">
      {blocks.map((block, index) => (
        <Fragment key={index}>{renderBlock(block)}</Fragment>
      ))}
    </div>
  );
}

type Block =
  | { type: "h"; level: number; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "p"; text: string };

function splitBlocks(raw: string): Block[] {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      out.push({ type: "h", level: heading[1].length, text: heading[2].trim() });
      i += 1;
      continue;
    }
    if (/^[-*•]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*•]\s+/, "").trim());
        i += 1;
      }
      out.push({ type: "ul", items });
      continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+[.)]\s+/, "").trim());
        i += 1;
      }
      out.push({ type: "ol", items });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3})\s+/.test(lines[i]) && !/^[-*•]\s+/.test(lines[i]) && !/^\d+[.)]\s+/.test(lines[i])) {
      para.push(lines[i].trim());
      i += 1;
    }
    out.push({ type: "p", text: para.join(" ") });
  }
  return out;
}

function renderBlock(block: Block): ReactNode {
  if (block.type === "h") {
    if (block.level === 1) return <h3 className="md-h">{inlineFormat(block.text)}</h3>;
    if (block.level === 2) return <h4 className="md-h">{inlineFormat(block.text)}</h4>;
    return <h5 className="md-h">{inlineFormat(block.text)}</h5>;
  }
  if (block.type === "ul") {
    return (
      <ul className="md-ul">
        {block.items.map((item, i) => (
          <li key={i}>{inlineFormat(item)}</li>
        ))}
      </ul>
    );
  }
  if (block.type === "ol") {
    return (
      <ol className="md-ol">
        {block.items.map((item, i) => (
          <li key={i}>{inlineFormat(item)}</li>
        ))}
      </ol>
    );
  }
  return <p className="md-p">{inlineFormat(block.text)}</p>;
}

function inlineFormat(text: string): ReactNode {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<code key={key++}>{token.slice(1, -1)}</code>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length ? parts : text;
}
