const sizes = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-8 w-8" };

export default function LoadingSpinner({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div className="flex items-center justify-center py-12">
      <div
        className={`${sizes[size]} animate-spin rounded-full border-2 border-zinc-200 dark:border-zinc-700 border-t-violet-500`}
      />
    </div>
  );
}
