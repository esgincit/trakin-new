import { redirect } from "next/navigation";

/** The old "request a workspace" form is gone: anyone creates an account, then their company (the platform activates it). */
export default function Signup() {
  redirect("/create-account");
}
