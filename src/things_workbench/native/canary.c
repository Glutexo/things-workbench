// Synthetic local denial probes. No credential lookup or external endpoint.
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <arpa/inet.h>
#include <sandbox.h>
// Public SDK no longer exposes this policy query; declare only this C ABI.
extern int sandbox_check(pid_t, const char *, int, ...);
static int refused(int fd) { int e=errno; if(fd>=0)close(fd); return fd<0 && (e==EPERM || e==EACCES); }
static int net(int type) {
    int fd=socket(AF_INET,type,0); if(fd<0)return errno==EPERM || errno==EACCES;
    struct sockaddr_in address={0}; address.sin_len=sizeof(address);address.sin_family=AF_INET;address.sin_port=htons(9);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    int result=connect(fd,(struct sockaddr *)&address,sizeof(address));int e=errno;close(fd);
    return result<0 && (e==EPERM || e==EACCES);
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    int rd=refused(open(argv[1],O_RDONLY));
    int wr=refused(open(argv[1],O_WRONLY));
    int allowed=open(argv[2],O_CREAT|O_EXCL|O_WRONLY,0600); int ok=allowed>=0;
    if(allowed>=0){if(write(allowed,"canary",6)!=6)ok=0;close(allowed);}
    pid_t child=fork();int forkDenied=child<0 && errno==EPERM;
    if(child==0)_exit(0);if(child>0)waitpid(child,NULL,0);
    int tcp=net(SOCK_STREAM),udp=net(SOCK_DGRAM);
    // Policy-level only, deliberately not an actual request to securityd/app.
    int credential=sandbox_check(getpid(),"mach-lookup",1,"com.apple.securityd")!=0;
    int apple=sandbox_check(getpid(),"appleevent-send",0)!=0;
    printf("{\"read_denied\":%s,\"write_denied\":%s,\"fork_denied\":%s,\"tcp_denied\":%s,\"udp_denied\":%s,\"credential_policy_denied\":%s,\"appleevent_policy_denied\":%s,\"allowed_write\":%s}\n",rd?"true":"false",wr?"true":"false",forkDenied?"true":"false",tcp?"true":"false",udp?"true":"false",credential?"true":"false",apple?"true":"false",ok?"true":"false");
    return rd && wr && forkDenied && tcp && udp && credential && apple && ok ? 0 : 1;
}
