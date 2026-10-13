/** Where a record of a given type opens in the web app. */
export function linkFor(refType: string, id: string): string {
  switch (refType) {
    case "invoice": return `/invoices/${id}`;
    case "sow": return `/contracts/sows/${id}`;
    case "agreement": return `/contracts/agreements/${id}`;
    case "consultant": return `/consultants/${id}`;
    case "company": return `/companies/${id}`;
    case "tracked_document": return `/compliance?doc=${id}`;
    case "envelope": return `/esign/${id}`;
    case "project": return `/projects/${id}`;
    default: return "/dashboard";
  }
}
