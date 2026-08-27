type Props = {
  name?: string | null;
  src?: string | null;
  className?: string;
};

export default function ProfileAvatar({ name = "User", src, className = "h-10 w-10 text-sm" }: Props) {
  const displayName = name?.trim() || "User";
  const initial = displayName.charAt(0).toUpperCase();
  return <span className={`profile-avatar ${className}`} aria-label={`${displayName} profile image`}>
    {src ? <Image src={src} alt="" fill sizes="80px" /> : initial}
  </span>;
}
import Image from "next/image";
