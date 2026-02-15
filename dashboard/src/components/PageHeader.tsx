interface Props {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}

export default function PageHeader({ title, subtitle, children }: Props) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h2 className="text-2xl font-bold">{title}</h2>
        {subtitle && (
          <p className="text-sm text-base-content/50 mt-0.5">{subtitle}</p>
        )}
      </div>
      {children && <div className="flex gap-2">{children}</div>}
    </div>
  );
}
