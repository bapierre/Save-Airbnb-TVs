import TVCastKit
import Foundation
exit((runSelfTests() + runServerSelfTest() + runSessionSelfTest() + runCaptureSelfTest()) == 0 ? 0 : 1)
