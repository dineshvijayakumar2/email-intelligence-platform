import React, { PropsWithChildren, useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard, Mail, Building2, Users, Lightbulb, Settings,
  Menu, X, LogOut, ChevronDown, Search, Bot, Zap, BarChart3,
  FolderOpen, AlertTriangle, Activity, Database, Brain, BookOpen, Filter,
  Shield, FileText, Cpu, Link2, Eye, ScrollText,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger, DropdownMenuLabel,
  DropdownMenuGroup,
} from '@/components/ui/dropdown-menu';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { StatusBadge } from '@/components/ui/status-badge';
import { useClient } from '../contexts/ClientContext';

// Role config
const roleConfig: Record<string, { label: string; variant: 'warning' | 'info' | 'success' }> = {
  admin: { label: 'Admin', variant: 'warning' },
  client_manager: { label: 'Client Manager', variant: 'info' },
  account_manager: { label: 'Account Manager', variant: 'success' },
};

// Navigation structure
interface NavItem {
  label: string;
  href?: string;
  icon: React.ReactNode;
  children?: { label: string; href: string; icon?: React.ReactNode; group?: string }[];
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/', icon: <LayoutDashboard className="h-4 w-4" /> },
  { label: 'Emails', href: '/emails', icon: <Mail className="h-4 w-4" /> },
  {
    label: 'Customers', icon: <Building2 className="h-4 w-4" />,
    children: [
      { label: 'Companies', href: '/customers', icon: <Building2 className="h-3.5 w-3.5" /> },
      { label: 'Contacts', href: '/customers/contacts', icon: <Users className="h-3.5 w-3.5" /> },
      { label: 'Threads', href: '/customers/threads', icon: <FolderOpen className="h-3.5 w-3.5" /> },
    ],
  },
  {
    label: 'Insights', icon: <Lightbulb className="h-4 w-4" />,
    children: [
      // Intelligence
      { label: 'Smart Inbox', href: '/insights/inbox', icon: <Mail className="h-3.5 w-3.5" />, group: 'Intelligence' },
      { label: 'Opportunities', href: '/insights/opportunities', icon: <Zap className="h-3.5 w-3.5" /> },
      { label: 'Email Rules', href: '/insights/email-rules', icon: <Filter className="h-3.5 w-3.5" /> },
      // Reports
      { label: 'Daily Digest', href: '/insights/digest', icon: <BookOpen className="h-3.5 w-3.5" />, group: 'Reports' },
      { label: 'Strategic Digest', href: '/insights/strategic', icon: <BarChart3 className="h-3.5 w-3.5" /> },
      // Tools
      { label: 'Semantic Search', href: '/insights/search', icon: <Search className="h-3.5 w-3.5" />, group: 'Tools' },
      { label: 'AI Assistant', href: '/insights/agent', icon: <Bot className="h-3.5 w-3.5" /> },
    ],
  },
  {
    label: 'Manage', icon: <Settings className="h-4 w-4" />,
    children: [
      { label: 'Mailboxes', href: '/mailboxes', icon: <Mail className="h-3.5 w-3.5" />, group: 'Setup' },
      { label: 'Clients', href: '/clients', icon: <Building2 className="h-3.5 w-3.5" /> },
      { label: 'Extraction', href: '/manage/extraction', icon: <Cpu className="h-3.5 w-3.5" /> },
      { label: 'Processing Jobs', href: '/manage/processing', icon: <Activity className="h-3.5 w-3.5" />, group: 'Operations' },
      { label: 'Error Logs', href: '/manage/errors', icon: <AlertTriangle className="h-3.5 w-3.5" /> },
      { label: 'Response Times', href: '/manage/response-times', icon: <BarChart3 className="h-3.5 w-3.5" />, group: 'Analytics' },
      { label: 'Data Health', href: '/manage/data-health', icon: <Activity className="h-3.5 w-3.5" /> },
      { label: 'Settings', href: '/settings', icon: <Settings className="h-3.5 w-3.5" />, group: 'Config' },
    ],
  },
  {
    label: 'Admin', icon: <Shield className="h-4 w-4" />, adminOnly: true,
    children: [
      { label: 'AI Usage', href: '/manage/ai-usage', icon: <Zap className="h-3.5 w-3.5" /> },
      { label: 'AI Playground', href: '/manage/ai-playground', icon: <Brain className="h-3.5 w-3.5" /> },
      { label: 'QB Config', href: '/manage/quickbase', icon: <Database className="h-3.5 w-3.5" /> },
      { label: 'QB Data', href: '/manage/quickbase-data', icon: <Database className="h-3.5 w-3.5" /> },
      { label: 'QB Match Review', href: '/manage/quickbase-matches', icon: <Link2 className="h-3.5 w-3.5" /> },
      { label: 'Intelligence Config', href: '/manage/intelligence-config', icon: <Brain className="h-3.5 w-3.5" /> },
      { label: 'Log Monitor', href: '/manage/logs', icon: <ScrollText className="h-3.5 w-3.5" /> },
      { label: 'Users', href: '/users', icon: <Users className="h-3.5 w-3.5" /> },
      { label: 'Data View', href: '/admin/data', icon: <Eye className="h-3.5 w-3.5" /> },
      { label: 'Audit Logs', href: '/admin/audit-logs', icon: <FileText className="h-3.5 w-3.5" /> },
    ],
  },
];

export const Layout: React.FC<PropsWithChildren> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { profile, signOut, isAdmin } = useAuth();
  const { clientId, setClientId, clients, clientName } = useClient();
  const [isMobile, setIsMobile] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth <= 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  useEffect(() => { setSheetOpen(false); }, [location.pathname]);

  const handleSignOut = async () => {
    await signOut();
    navigate('/login', { replace: true });
  };

  const getUserInitials = () => {
    if (profile?.name) {
      const names = profile.name.split(' ');
      return names.length >= 2
        ? `${names[0][0]}${names[1][0]}`.toUpperCase()
        : profile.name.substring(0, 2).toUpperCase();
    }
    return 'U';
  };

  const isActive = (href?: string) => {
    if (!href) return false;
    if (href === '/') return location.pathname === '/';
    return location.pathname.startsWith(href);
  };

  const filteredNav = navItems.filter(item => !item.adminOnly || isAdmin);

  // Desktop nav item renderer
  const NavLink = ({ item }: { item: NavItem }) => {
    if (item.children) {
      const active = item.children.some(c => isActive(c.href));
      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className={cn(
              'inline-flex items-center gap-1.5 h-8 px-3 text-[13px] font-medium rounded-md transition-all duration-150',
              active
                ? 'text-white bg-primary shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100',
            )}>
              {item.icon}
              {item.label}
              <ChevronDown className={cn('h-3 w-3', active ? 'opacity-70' : 'opacity-40')} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" sideOffset={8} className="w-56 shadow-xl border border-slate-200 rounded-lg">
            {item.children.map((child, idx) => (
              <React.Fragment key={child.href}>
                {child.group && (
                  <>
                    {idx > 0 && <DropdownMenuSeparator />}
                    <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-slate-400 font-medium px-3 py-1">
                      {child.group}
                    </DropdownMenuLabel>
                  </>
                )}
                <DropdownMenuItem onClick={() => navigate(child.href)}
                  className={cn(
                    'gap-2.5 py-2 px-3 cursor-pointer',
                    isActive(child.href) ? 'bg-primary/5 text-primary font-medium' : 'text-slate-600',
                  )}>
                  {child.icon && <span className={isActive(child.href) ? 'text-primary' : 'text-slate-400'}>{child.icon}</span>}
                  {child.label}
                </DropdownMenuItem>
              </React.Fragment>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      );
    }

    return (
      <Link to={item.href!} className={cn(
        'inline-flex items-center gap-1.5 h-8 px-3 text-[13px] font-medium rounded-md transition-all duration-150',
        isActive(item.href)
          ? 'text-white bg-primary shadow-sm'
          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100',
      )}>
        {item.icon}
        {item.label}
      </Link>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Top bar */}
      <header className="sticky top-0 z-50 w-full bg-white border-b border-slate-200/60 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
        {/* Accent bar */}
        <div className="h-[2px] bg-gradient-to-r from-primary via-accent to-primary/60" />

        <div className="flex h-12 items-center px-5 gap-5">
          {/* Mobile menu trigger */}
          {isMobile && (
            <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
              <SheetTrigger asChild>
                <button className="p-2 -ml-2 text-slate-600 hover:text-slate-900">
                  <Menu className="h-5 w-5" />
                </button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 p-0">
                <div className="flex flex-col h-full">
                  {/* Mobile header */}
                  <div className="flex items-center gap-3 px-4 py-3 border-b">
                    <span className="text-lg">📧</span>
                    <div>
                      <p className="text-sm font-semibold">Email Intelligence</p>
                      <p className="text-xs text-slate-500">Analytics Platform</p>
                    </div>
                  </div>

                  {/* Mobile nav */}
                  <div className="flex-1 overflow-y-auto py-2">
                    {filteredNav.map(item => (
                      <div key={item.label}>
                        {item.href ? (
                          <Link to={item.href} onClick={() => setSheetOpen(false)}
                            className={cn(
                              'flex items-center gap-3 px-4 py-2.5 text-sm',
                              isActive(item.href) ? 'text-primary bg-primary/5 font-medium' : 'text-slate-600 hover:bg-slate-50',
                            )}>
                            {item.icon}
                            {item.label}
                          </Link>
                        ) : (
                          <>
                            <p className="px-4 pt-4 pb-1 text-xs font-medium uppercase tracking-wider text-slate-400">
                              {item.label}
                            </p>
                            {item.children?.map(child => (
                              <Link key={child.href} to={child.href} onClick={() => setSheetOpen(false)}
                                className={cn(
                                  'flex items-center gap-3 px-6 py-2 text-sm',
                                  isActive(child.href) ? 'text-primary bg-primary/5 font-medium' : 'text-slate-600 hover:bg-slate-50',
                                )}>
                                {child.icon}
                                {child.label}
                              </Link>
                            ))}
                          </>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Mobile user + logout */}
                  <div className="border-t p-4">
                    {profile && (
                      <div className="flex items-center gap-3 mb-3">
                        <Avatar className="h-9 w-9">
                          <AvatarImage src={profile.avatarUrl} />
                          <AvatarFallback className="bg-primary text-white text-xs">{getUserInitials()}</AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="text-sm font-medium">{profile.name}</p>
                          <div className="flex gap-1 mt-0.5">
                            {profile.roles?.map(role => (
                              <StatusBadge key={role} variant={roleConfig[role]?.variant || 'neutral'} size="sm">
                                {roleConfig[role]?.label || role}
                              </StatusBadge>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                    <button onClick={handleSignOut}
                      className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-md">
                      <LogOut className="h-4 w-4" />
                      Sign Out
                    </button>
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          )}

          {/* Brand */}
          <Link to="/" className="flex items-center gap-2.5 shrink-0 group">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
              <Mail className="h-3.5 w-3.5 text-white" />
            </div>
            {!isMobile && (
              <span className="text-[13px] font-bold text-slate-800 tracking-tight">
                Email Intelligence
              </span>
            )}
          </Link>

          {/* Nav divider */}
          {!isMobile && <div className="w-px h-5 bg-slate-200/70" />}

          {/* Desktop nav */}
          {!isMobile && (
            <nav className="flex items-center gap-1">
              {filteredNav.map(item => <NavLink key={item.label} item={item} />)}
            </nav>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 px-2 py-1 rounded-full hover:bg-slate-100/80 transition-all duration-200 border border-transparent hover:border-slate-200/60">
                <Avatar className="h-7 w-7">
                  <AvatarImage src={profile?.avatarUrl} />
                  <AvatarFallback className="bg-primary text-white text-[10px] font-medium">{getUserInitials()}</AvatarFallback>
                </Avatar>
                {!isMobile && (
                  <>
                    <div className="text-left">
                      <span className="text-[13px] font-medium text-slate-700 block leading-tight">{profile?.name || 'User'}</span>
                      {clientName && <span className="text-[10px] text-slate-400 block leading-tight">{clientName}</span>}
                    </div>
                    <ChevronDown className="h-3 w-3 text-slate-300" />
                  </>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>
                <p className="text-sm font-medium">{profile?.name}</p>
                <p className="text-xs text-muted-foreground">{profile?.email}</p>
                {profile?.roles && (
                  <div className="flex gap-1 mt-1.5">
                    {profile.roles.map(role => (
                      <StatusBadge key={role} variant={roleConfig[role]?.variant || 'neutral'} size="sm">
                        {roleConfig[role]?.label || role}
                      </StatusBadge>
                    ))}
                  </div>
                )}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {/* Client switcher */}
              {clients.length > 0 && (
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-slate-400 font-medium pb-0">Client</DropdownMenuLabel>
                  <div className="px-2 py-1.5">
                    <select
                      value={clientId}
                      onChange={e => setClientId(e.target.value)}
                      className="w-full h-7 px-2 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-primary/20"
                    >
                      {clients.map(c => <option key={c.id} value={c.id}>{c.client_name}</option>)}
                    </select>
                  </div>
                </DropdownMenuGroup>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleSignOut} className="text-red-600 focus:text-red-600">
                <LogOut className="h-4 w-4 mr-2" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Main content */}
      <main className="min-h-[calc(100vh-56px)]">
        {children}
      </main>
    </div>
  );
};
