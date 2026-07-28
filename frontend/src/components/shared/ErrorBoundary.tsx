/* ================================================================
   ErrorBoundary — Catches uncaught React render errors gracefully
   ================================================================ */

import { Component, type ErrorInfo, type ReactNode } from 'react'
import styles from './ErrorBoundary.module.css'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.boundary}>
          <div className={styles.card}>
            <span className={styles.icon}>⚠️</span>
            <h2 className={styles.title}>Something went wrong</h2>
            <p className={styles.message}>
              {this.state.error?.message || 'An unexpected error occurred in this section.'}
            </p>
            <pre className={styles.stack}>
              {this.state.error?.stack?.split('\n').slice(0, 5).join('\n')}
            </pre>
            <button className={styles.retryBtn} onClick={this.handleReload}>
              🔄 Try Again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
