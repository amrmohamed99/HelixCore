/* ================================================================
   PageTransition — wraps page content with a subtle fade+slide in.
   Use with a `key` prop tied to location.pathname so it remounts
   on route change, triggering the CSS animation.
   ================================================================ */

import type { ReactNode } from 'react'
import pt from './PageTransition.module.css'

interface Props {
  children: ReactNode
}

export default function PageTransition({ children }: Props) {
  return <div className={pt.wrapper}>{children}</div>
}
