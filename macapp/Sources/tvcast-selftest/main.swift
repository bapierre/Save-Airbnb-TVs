import TVCastKit
import Foundation
exit((runSelfTests() + runServerSelfTest() + runSessionSelfTest()) == 0 ? 0 : 1)
