interface Props {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}

export default function PageHeader({ title, subtitle, children }: Props) {
  return (
    <div className="flex items-center justify-between pb-4 mb-6 border-b border-base-content/5">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {subtitle && (
          <p className="text-sm text-base-content/40 mt-0.5">{subtitle}</p>
        )}
      </div>
      {children && <div className="flex gap-2">{children}</div>}
    </div>
  );
}
