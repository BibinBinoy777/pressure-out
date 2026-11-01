import React from "react";

export interface ContainerProps {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "section" | "header" | "footer";
}

export function Container({
  children,
  className = "",
  as: Component = "div",
}: ContainerProps) {
  return (
    <Component className={`mx-auto w-full max-w-5xl px-4 sm:px-6 lg:px-8 ${className}`.trim()}>
      {children}
    </Component>
  );
}
