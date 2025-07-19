// card.jsx – ein extrem simples Card-Wrapper
export function Card({ className = "", children, ...rest }) {
    return (
      <div className={`rounded-xl shadow border bg-white ${className}`} {...rest}>
        {children}
      </div>
    );
  }
  
  export function CardContent({ className = "", children, ...rest }) {
    return (
      <div className={`p-4 ${className}`} {...rest}>
        {children}
      </div>
    );
  }
  