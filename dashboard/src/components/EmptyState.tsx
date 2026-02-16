import { Archive } from "@phosphor-icons/react";

interface Props {
  message: string;
}

export default function EmptyState({ message }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-base-content/30">
      <Archive size={40} className="mb-3" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
