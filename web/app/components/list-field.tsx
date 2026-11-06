'use client';

import { useEffect, useState } from 'react';

function parse(text: string): string[] {
  return text.split(/[\n,]/).map((part) => part.trim()).filter(Boolean);
}

/** A comma-separated list editor that keeps what you type, including trailing commas. */
export default function ListField({
  value,
  onChange,
  rows = 2,
  placeholder,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  rows?: number;
  placeholder?: string;
}) {
  const [text, setText] = useState(value.join(', '));

  useEffect(() => {
    // Only overwrite the text when the list was changed from outside (for example by a CV upload).
    setText((current) => (parse(current).join('|') === value.join('|') ? current : value.join(', ')));
  }, [value]);

  return (
    <textarea
      rows={rows}
      value={text}
      placeholder={placeholder}
      onChange={(event) => {
        setText(event.target.value);
        onChange(parse(event.target.value));
      }}
    />
  );
}
