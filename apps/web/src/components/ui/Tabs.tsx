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
    // The row scrolls within itself rather than widening the page. Six tabs
    // (trip detail, since the Map tab) do not fit at 390px, and without this
    // the overflow pushed the whole document to 458px wide.
    <div
      role="tablist"
      className="flex gap-md overflow-x-auto border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
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
              "-mb-px shrink-0 border-b-2 px-xs pb-sm text-sm font-bold transition",
              isActive
                ? "border-lime text-ink"
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
