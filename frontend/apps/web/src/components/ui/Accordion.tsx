import React from 'react';
import * as RadixAccordion from '@radix-ui/react-accordion';
import { ChevronDown } from 'lucide-react';

interface Props {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export default function Accordion({ title, children, defaultOpen = false }: Props) {
  const value = React.useId();
  return (
    <RadixAccordion.Root type="multiple" defaultValue={defaultOpen ? [value] : []} className="border rounded-lg">
      <RadixAccordion.Item value={value}>
        <RadixAccordion.Header>
          <RadixAccordion.Trigger className="w-full flex justify-between items-center px-4 py-2 bg-gray-100 hover:bg-gray-200">
            <span>{title}</span>
            <ChevronDown className="transition-transform duration-200 [data-state=open]:rotate-180" />
          </RadixAccordion.Trigger>
        </RadixAccordion.Header>
        <RadixAccordion.Content className="p-4">
          {children}
        </RadixAccordion.Content>
      </RadixAccordion.Item>
    </RadixAccordion.Root>
  );
}
