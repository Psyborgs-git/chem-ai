import { useId, type InputHTMLAttributes } from "react";

export function Checkbox({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const id = useId();
  return (
    <div className="cs-checkbox">
      <input id={id} type="checkbox" {...props} />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}
