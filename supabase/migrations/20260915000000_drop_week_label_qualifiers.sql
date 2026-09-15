-- Drop the "(Step-Back)" and "(Taper)" qualifiers from week labels, leaving
-- plain "Week 14", "Week 16", "Week 17". The race week keeps its marker, so
-- "Week 18 🏁 Race" is deliberately left alone -- it's the only week meant to
-- read as anything other than its number.
--
-- Edits the label in place rather than rewriting the whole weeks blob, so
-- nothing else in the plan can be disturbed. WITH ORDINALITY preserves the
-- original array order through the unnest/re-aggregate round trip.

update plans p set
  weeks = (
    select jsonb_agg(
             case
               when w.value->>'label' ~ ' \((Step-Back|Taper)\)$'
               then jsonb_set(
                      w.value,
                      '{label}',
                      to_jsonb(regexp_replace(w.value->>'label',
                                              ' \((Step-Back|Taper)\)$', ''))
                    )
               else w.value
             end
             order by w.ord
           )
    from jsonb_array_elements(p.weeks) with ordinality as w(value, ord)
  ),
  updated_at = now()
where p.id = 'chicago_2026';
