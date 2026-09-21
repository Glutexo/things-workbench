import Foundation
// Build-pinned bridge: Swift calling convention, no Objective-C cast of Swift ABI.
extension NSObject {
    @_silgen_name("$s11ThingsModel22THMSyncronyCoordinatorC5store9serverURL13appIdentifier0H10InstanceId19usingLegacySyncronyAC4Base7BSStoreC_10Foundation0G0VS2SSbtcfC")
    static func offlineCoordinator(store: __owned AnyObject, serverURL: __owned URL, appIdentifier: __owned String, appInstanceId: __owned String, usingLegacySyncrony: Bool) -> AnyObject
    @_silgen_name("$s4Base21BSSyncronyCoordinatorC14syncControllerSo06SYSyncE8Protocol_pvg")
    func offlineController() -> AnyObject
}
@_cdecl("twb_coordinator")
func coordinator(_ p: UnsafeMutableRawPointer) -> UnsafeMutableRawPointer? {
    guard let cls = NSClassFromString("_TtC11ThingsModel22THMSyncronyCoordinator") as? NSObject.Type else { return nil }
    let store = Unmanaged<AnyObject>.fromOpaque(p).takeUnretainedValue()
    let result = cls.offlineCoordinator(store: store, serverURL: URL(string: "https://invalid.invalid/")!, appIdentifier: "things-workbench-copy", appInstanceId: "things-workbench-copy", usingLegacySyncrony: false)
    return Unmanaged.passRetained(result).toOpaque()
}
@_cdecl("twb_controller")
func controller(_ p: UnsafeMutableRawPointer) -> UnsafeMutableRawPointer {
    let coordinator = Unmanaged<NSObject>.fromOpaque(p).takeUnretainedValue()
    return Unmanaged.passRetained(coordinator.offlineController()).toOpaque()
}
