/// The two inspections a driver completes pre-trip and the evidence types
/// that feed into each.
///
/// One inspection can be answered by multiple evidence photos. Each photo
/// goes through the model independently; the app composes the per-photo
/// verdicts into an inspection-level verdict (see
/// `state/composition.dart`). The model's per-photo contract is the
/// existing `shared/schemas/<schemaId>.json` — the v5 schema audit will
/// later sharpen field names without changing this two-inspection shape.
library;

enum Inspection {
  fifthWheelCoupling(
    label: 'Front coupling',
    description: 'Fifth wheel coupling between tractor and trailer.',
  ),
  pintleHook(
    label: 'Rear hitch',
    description: 'Pintle hook + safety chains at the rear of the trailer.',
  );

  const Inspection({required this.label, required this.description});

  final String label;
  final String description;

  List<EvidenceType> get evidenceTypes =>
      EvidenceType.values.where((e) => e.inspection == this).toList();

  List<EvidenceType> get requiredEvidence =>
      evidenceTypes.where((e) => e.isRequired).toList();

  List<EvidenceType> get optionalEvidence =>
      evidenceTypes.where((e) => !e.isRequired).toList();

  /// The dominant / primary evidence type for this inspection. A pass
  /// from this evidence type alone is sufficient for a confident verdict
  /// (with a `side_view_only`-style flag); other evidence types are
  /// optional confirmation.
  EvidenceType get dominantEvidence =>
      evidenceTypes.firstWhere((e) => e.isDominant);
}

enum EvidenceType {
  sideView(
    inspection: Inspection.fifthWheelCoupling,
    label: 'Side view',
    instruction:
        'Stand at the side of the tractor and frame the gap between the '
        'trailer apron and the fifth wheel plate.',
    schemaId: 'fifth_wheel_side_view',
    schemaAsset: 'assets/schemas/fifth_wheel_side_view.json',
    isRequired: true,
    isDominant: true,
    showsTargetOverlay: true,
  ),
  lockJawsUnderneath(
    inspection: Inspection.fifthWheelCoupling,
    label: 'Lock jaws (underneath)',
    instruction:
        'Crouch behind the cab and frame the lock jaws closed around the '
        'kingpin shank. Optional confirmation — skip if the angle is hard.',
    schemaId: 'lock_jaws_closeup',
    schemaAsset: 'assets/schemas/lock_jaws_closeup.json',
    isRequired: false,
    isDominant: false,
    showsTargetOverlay: false,
  ),
  rearAssembly(
    inspection: Inspection.pintleHook,
    label: 'Pintle hook + chains',
    instruction:
        'Frame the pintle hook, safety pin, and both safety chains in a '
        'single shot.',
    schemaId: 'pintle_hook_and_chains',
    schemaAsset: 'assets/schemas/pintle_hook_and_chains.json',
    isRequired: true,
    isDominant: true,
    showsTargetOverlay: false,
  );

  const EvidenceType({
    required this.inspection,
    required this.label,
    required this.instruction,
    required this.schemaId,
    required this.schemaAsset,
    required this.isRequired,
    required this.isDominant,
    required this.showsTargetOverlay,
  });

  final Inspection inspection;
  final String label;
  final String instruction;

  /// Matches `shared/schemas/<schemaId>.json`'s `category.const`.
  final String schemaId;
  final String schemaAsset;

  /// At least one required evidence type per inspection is necessary for
  /// the inspection to be "ready to compose."
  final bool isRequired;

  /// The "load-bearing" evidence type for this inspection. Used to decide
  /// composed confidence ("side_view_only" vs "high").
  final bool isDominant;

  /// Whether the capture screen draws a target rectangle on the preview.
  /// Currently only the side view gets one — it's the load-bearing shot
  /// and the framing target is unambiguous.
  final bool showsTargetOverlay;
}
