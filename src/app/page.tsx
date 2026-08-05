import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Temporary landing page — "/" is not in the route spec (candidates enter at
// /book from the main site), so this just points people the right way.
export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-24 text-center">
           Base routes
    </main>
  );
}
