import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, LogOut, Settings, UserRound } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TextSizeToggle } from "@/components/TextSizeToggle";
import { useSession } from "@/lib/session";
import { initials } from "@/lib/format";
import { roleWords } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Name, roles, theme toggle, text size, Settings, Activity, Sign out. */
export function ProfileMenu({ className }: { className?: string }) {
  const { me, signOut } = useSession();
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);
  if (!me) return null;
  const name = me.display_name || me.user;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={cn("rounded-full outline-none ring-offset-2 ring-offset-background transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-ring active:scale-95", className)} aria-label={`Your menu, ${name}`}>
          <Avatar className="size-9 border border-border">
            {me.profile?.photo ? <AvatarImage src={me.profile.photo} alt="" /> : null}
            <AvatarFallback className="bg-secondary text-sm font-bold text-secondary-foreground">{initials(name)}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-bold text-foreground">{name}</p>
          <p className="truncate text-xs text-muted-foreground">{me.user}</p>
          <p className="mt-1 flex flex-wrap gap-1">
            {roleWords(me).map((r) => <span key={r} className="quote-chip">{r}</span>)}
          </p>
          {me.hospital?.name ? <p className="mt-1 truncate text-xs text-muted-foreground">{me.hospital.name}</p> : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="flex items-center justify-between gap-2 px-2 py-1.5" onKeyDown={(e) => e.stopPropagation()}>
          <span className="text-sm">Theme</span>
          <ThemeToggle withLabel />
        </div>
        <div className="flex items-center justify-between gap-2 px-2 py-1.5" onKeyDown={(e) => e.stopPropagation()}>
          <span className="text-sm">Text size</span>
          <TextSizeToggle />
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link to="/settings"><Settings className="size-4" aria-hidden /> Settings</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link to="/settings#profile"><UserRound className="size-4" aria-hidden /> My profile</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link to="/activity"><Activity className="size-4" aria-hidden /> Activity</Link></DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={leaving} onSelect={async (e) => { e.preventDefault(); setLeaving(true); await signOut(); navigate("/sign-in", { replace: true }); }}>
          <LogOut className="size-4" aria-hidden /> {leaving ? "Signing out" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
