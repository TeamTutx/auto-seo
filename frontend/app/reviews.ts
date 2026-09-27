/** What customers have said about Signal, in their own words.
 *
 *  **Empty on purpose, and it renders nothing while it is.** Signal has a
 *  handful of accounts and no one has been asked for a quote yet, and an
 *  invented testimonial is both dishonest and the first thing a sceptical reader
 *  checks - a name that belongs to nobody ends a sale as surely as a stock
 *  headshot does. The section below simply does not appear until this list has
 *  something real in it, so the page never claims otherwise.
 *
 *  To add one: get the person's permission for their name and their words, paste
 *  them verbatim, and do not tidy the wording - the unevenness is most of what
 *  makes a real quote read as real. Two genuine sentences are worth more than a
 *  page of invented ones.
 */
export interface Review {
  /** Their words, unedited. */
  quote: string;
  /** A real person who agreed to be named. */
  name: string;
  /** What they do, or their site. Optional. */
  role?: string;
  /** Somewhere the reader can confirm they exist, if they are happy to be linked. */
  url?: string;
}

export const REVIEWS: Review[] = [];
