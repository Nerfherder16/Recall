export default function LoadingSpinner({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div className="flex items-center justify-center py-12">
      <span className={`loading loading-spinner loading-${size}`} />
    </div>
  );
}
