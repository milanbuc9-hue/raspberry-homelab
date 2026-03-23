'use client'
import AppNav from '@/components/AppNav'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950">
      <AppNav />
      {/* Offset for sidebar on md+, bottom nav padding on mobile */}
      <div className="md:ml-56 pb-20 md:pb-0">
        {children}
      </div>
    </div>
  )
}
