/**
 * The API serves naive wall-clock datetimes (no offset). Pin them to UTC so we
 * render the time exactly as scheduled (the local departure-board time), not
 * shifted into the viewer's timezone.
 */
export function toUtcDate(iso: string): Date {
    return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) || !iso.includes("T") ? iso : `${iso}Z`);
}
