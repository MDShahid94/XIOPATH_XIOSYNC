import React from 'react';

/**
 * Global Error Boundary (F-08)
 * Catches any React render error and shows a friendly recovery UI
 * instead of the entire app crashing to a white screen.
 */
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        this.setState({ errorInfo });
        console.error("ErrorBoundary caught:", error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minHeight: '60vh',
                    padding: '40px',
                    textAlign: 'center',
                    fontFamily: 'Inter, system-ui, sans-serif',
                }}>
                    <div style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '12px',
                        padding: '32px 48px',
                        maxWidth: '500px',
                    }}>
                        <h2 style={{ color: '#EF4444', margin: '0 0 12px 0', fontSize: '1.5rem' }}>
                            Something went wrong
                        </h2>
                        <p style={{ color: '#9CA3AF', margin: '0 0 20px 0', fontSize: '0.9rem' }}>
                            {this.state.error?.message || 'An unexpected error occurred.'}
                        </p>
                        <button
                            onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
                            style={{
                                background: 'linear-gradient(135deg, #6366F1, #8B5CF6)',
                                color: 'white',
                                border: 'none',
                                padding: '10px 24px',
                                borderRadius: '8px',
                                cursor: 'pointer',
                                fontWeight: '600',
                                fontSize: '0.9rem',
                            }}
                        >
                            Try Again
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}

export default ErrorBoundary;
