import "server-only";

/** Server time for a render: the client measures its clock offset against this. */
export const serverNow = () => Date.now();
