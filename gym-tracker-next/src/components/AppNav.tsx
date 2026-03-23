'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const links = [
  { href: '/dashboard', label: 'Workouts', icon: '🏋️' },
  { href: '/calories', label: 'Kalorien', icon: '🥗' },
  { href: '/todos', label: 'Todos', icon: '✅' },
  { href: '/feed', label: 'Feed', icon: '📸' },
  { href: '/profile', label: 'Profil', icon: '👤' },
]

export default function AppNav() {
  const pathname = usePathname()

  return (
    <>
      {/* Mobile bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-gray-900 border-t border-gray-800 flex md:hidden">
        {links.map(link => {
          const active = pathname === link.href || pathname.startsWith(link.href + '/')
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex-1 flex flex-col items-center justify-center py-2 gap-0.5 transition-colors ${
                active ? 'text-blue-400' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-xl leading-none">{link.icon}</span>
              <span className="text-[10px] font-medium">{link.label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Desktop sidebar */}
      <aside className="hidden md:flex fixed left-0 top-0 bottom-0 z-50 w-56 bg-gray-900 border-r border-gray-800 flex-col pt-6 pb-4">
        <div className="px-5 mb-8">
          <span className="text-lg font-bold text-white">Gym Tracker</span>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {links.map(link => {
            const active = pathname === link.href || pathname.startsWith(link.href + '/')
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium ${
                  active
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`}
              >
                <span className="text-lg leading-none">{link.icon}</span>
                <span>{link.label}</span>
              </Link>
            )
          })}
        </nav>
      </aside>
    </>
  )
}
