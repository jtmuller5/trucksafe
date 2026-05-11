/// The three pre-trip inspection steps.
///
/// Each carries the schema name (matching `shared/schemas/<x>.json`'s
/// `category.const` value), a short human label, and the per-step system
/// prompt that pairs with the schema asset.
enum InspectionCategory {
  fifthWheel(
    schemaId: 'fifth_wheel_side_view',
    label: 'Fifth wheel (side view)',
    instruction: 'Stand at the side of the tractor and frame the gap between '
        'the trailer apron and the fifth wheel plate.',
    schemaAsset: 'assets/schemas/fifth_wheel_side_view.json',
  ),
  lockJaws(
    schemaId: 'lock_jaws_closeup',
    label: 'Lock jaws (close-up)',
    instruction: 'Crouch behind the cab and frame the lock jaws closed around '
        'the kingpin shank.',
    schemaAsset: 'assets/schemas/lock_jaws_closeup.json',
  ),
  pintleHook(
    schemaId: 'pintle_hook_and_chains',
    label: 'Pintle hook + safety chains',
    instruction: 'Frame the pintle hook, safety pin, and both safety chains '
        'in a single shot.',
    schemaAsset: 'assets/schemas/pintle_hook_and_chains.json',
  );

  const InspectionCategory({
    required this.schemaId,
    required this.label,
    required this.instruction,
    required this.schemaAsset,
  });

  final String schemaId;
  final String label;
  final String instruction;
  final String schemaAsset;
}
