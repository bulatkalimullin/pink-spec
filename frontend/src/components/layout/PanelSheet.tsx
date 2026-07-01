import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface PanelSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}

export default function PanelSheet({
  open,
  onOpenChange,
  title,
  children,
  className,
}: PanelSheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={cn(
            "fixed z-50 flex flex-col bg-card shadow-lg",
            "inset-x-0 bottom-0 top-12 rounded-t-xl border border-border",
            "md:inset-y-0 md:left-auto md:right-0 md:top-0 md:w-full md:max-w-sm md:rounded-none md:rounded-l-xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
            "md:data-[state=closed]:slide-out-to-right md:data-[state=open]:slide-in-from-right",
            className
          )}
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <Dialog.Title className="text-sm font-semibold">{title}</Dialog.Title>
            <Dialog.Close className="rounded p-1 hover:bg-accent transition-colors">
              <X className="h-4 w-4 text-muted-foreground" />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
