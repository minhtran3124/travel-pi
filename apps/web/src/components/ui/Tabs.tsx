export interface Tab {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div role="tablist" className="flex gap-md border-b border-line">
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={[
              "-mb-px border-b-2 px-xs pb-sm text-sm font-bold transition",
              isActive
                ? "border-coral-bright text-ink"
                : "border-transparent text-muted hover:text-ink",
            ].join(" ")}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
