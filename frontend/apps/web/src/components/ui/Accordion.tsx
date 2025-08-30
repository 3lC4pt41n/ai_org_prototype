import React, { useState } from 'react';

interface Props {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export default function Accordion({ title, children, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border rounded-lg">
      <button
        className="w-full flex justify-between items-center px-4 py-2 bg-gray-100 hover:bg-gray-200"
        onClick={() => setOpen(!open)}
      >
        <span>{title}</span>
        <span className="text-xl leading-none">{open ? '−' : '+'}</span>
      </button>
      {open && <div className="p-4">{children}</div>}
    </div>
  );
}
